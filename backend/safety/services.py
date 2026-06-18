# backend/safety/services.py
import json
import gzip
import base64
import hashlib
from django.core.exceptions import ValidationError
from .constants import RiskLevel, HazardCategory, DecisionSource, RULE_ENGINE_VERSION

class VersionedRuleEngine:
    VERSION = RULE_ENGINE_VERSION

    @classmethod
    def evaluate(cls, category: str, labels: list) -> dict:
        """
        Applies deterministic rules to classify hazards before AI processing.
        Returns a dictionary if matching rules, or None.
        """
        category_lower = category.lower()
        labels_lower = [str(l).lower() for l in labels]

        # 1. Lithium Batteries
        if "lithium" in category_lower or any("lithium" in l for l in labels_lower) or "battery" in category_lower:
            return {
                "risk_level": RiskLevel.CRITICAL,
                "risk_score": 1.0,
                "decision_source": DecisionSource.RULE_ENGINE,
                "hazard_categories": [HazardCategory.LITHIUM_BATTERY, HazardCategory.BATTERY],
                "safety_flags": ["FIRE_HAZARD", "TOXIC_LEAK"],
                "safe_disposal_method": "Take to municipal hazardous waste collection or designated battery recycling drop-off point. Never dispose in landfill, crush, or burn.",
                "approved_upcycling": [],
                "blocked_upcycling": ["Any upcycling or open crushing is strictly blocked due to fire and chemical risks."],
                "review_required": True,
                "review_reason": "Lithium batteries present serious thermal runway and environmental toxin risk."
            }

        # 2. Medical Waste
        medical_keywords = {"syringe", "needle", "medical", "biohazard", "vial", "blood", "pharmaceutical"}
        if category_lower in medical_keywords or any(kw in category_lower for kw in medical_keywords) or any(any(kw in l for kw in medical_keywords) for l in labels_lower):
            return {
                "risk_level": RiskLevel.CRITICAL,
                "risk_score": 1.0,
                "decision_source": DecisionSource.RULE_ENGINE,
                "hazard_categories": [HazardCategory.MEDICAL, HazardCategory.BIOHAZARD, HazardCategory.SHARP_OBJECT],
                "safety_flags": ["BIOHAZARD_RISK", "SHARP_INJURY"],
                "safe_disposal_method": "Dispose of inside an approved biohazard sharps container immediately. Contact specialized biohazard collection.",
                "approved_upcycling": [],
                "blocked_upcycling": ["Medical items and biologics must never be reused or upcycled under any circumstances."],
                "review_required": True,
                "review_reason": "Medical and biological waste contains infection and physical injury risks."
            }

        # 3. Chemical / Corrosive
        chemical_keywords = {"chemical", "corrosive", "acid", "pesticide", "herbicide", "solvent", "bleach"}
        if category_lower in chemical_keywords or any(kw in category_lower for kw in chemical_keywords) or any(any(kw in l for kw in chemical_keywords) for l in labels_lower):
            return {
                "risk_level": RiskLevel.HIGH,
                "risk_score": 0.90,
                "decision_source": DecisionSource.RULE_ENGINE,
                "hazard_categories": [HazardCategory.CHEMICAL, HazardCategory.TOXIC, HazardCategory.CORROSIVE],
                "safety_flags": ["TOXIC_EXPOSURE", "CHEMICAL_CORROSION"],
                "safe_disposal_method": "Dispose at certified hazardous chemical collection location. Keep away from water sources.",
                "approved_upcycling": [],
                "blocked_upcycling": ["Upcycling chemical storage bottles poses toxic residue leaching risks."],
                "review_required": True,
                "review_reason": "Chemical container has toxic residues requiring manual evaluation."
            }

        # 4. Unknown / Mixed Waste
        if category_lower == "unknown" or "unknown" in category_lower:
            return {
                "risk_level": RiskLevel.HIGH,
                "risk_score": 0.80,
                "decision_source": DecisionSource.RULE_ENGINE,
                "hazard_categories": [HazardCategory.UNKNOWN],
                "safety_flags": ["UNKNOWN_HAZARDS"],
                "safe_disposal_method": "Isolate from general wastes and consult municipal hazardous inspectors.",
                "approved_upcycling": [],
                "blocked_upcycling": ["No upcycling allowed for items of unknown chemical/material composition."],
                "review_required": True,
                "review_reason": "Unknown material requires physical review to rule out hazardous contents."
            }

        return None


def validate_safety_output(data: dict) -> None:
    """
    Validates Gemini output payload structure and bounds.
    """
    required_fields = {
        "risk_level", "risk_score", "hazard_categories",
        "safe_disposal_method", "approved_upcycling",
        "blocked_upcycling", "review_required", "review_reason"
    }
    for field in required_fields:
        if field not in data:
            raise ValidationError(f"Missing required safety output field: '{field}'")

    # Risk level choices validation
    if data["risk_level"] not in RiskLevel.values:
        raise ValidationError(f"Invalid risk_level: '{data['risk_level']}'")

    # Risk score boundaries
    score = data["risk_score"]
    try:
        score_val = float(score)
        if not (0.0 <= score_val <= 1.0):
            raise ValidationError("risk_score must be between 0.0 and 1.0 inclusive.")
    except (ValueError, TypeError):
        raise ValidationError("risk_score must be a valid float value.")

    # Types verification
    if not isinstance(data["hazard_categories"], list):
        raise ValidationError("hazard_categories must be a list.")
    for hc in data["hazard_categories"]:
        if hc not in HazardCategory.values:
            raise ValidationError(f"Invalid hazard category: '{hc}'")

    if not isinstance(data["approved_upcycling"], list):
        raise ValidationError("approved_upcycling must be a list.")
    if not isinstance(data["blocked_upcycling"], list):
        raise ValidationError("blocked_upcycling must be a list.")


class AuditGCSService:
    @staticmethod
    def compress_payload(payload: dict) -> str:
        payload_str = json.dumps(payload, sort_keys=True)
        compressed = gzip.compress(payload_str.encode('utf-8'))
        return base64.b64encode(compressed).decode('utf-8')

    @staticmethod
    def decompress_payload(compressed_b64: str) -> dict:
        compressed = base64.b64decode(compressed_b64.encode('utf-8'))
        payload_str = gzip.decompress(compressed).decode('utf-8')
        return json.loads(payload_str)

    @classmethod
    def compute_hash(cls, payload: dict) -> str:
        payload_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(payload_str.encode('utf-8')).hexdigest()

    @classmethod
    def upload_to_gcs(cls, payload: dict, bucket_name: str = "wastetrack-audit") -> str:
        """
        Uploads compressed payload to GCS bucket.
        """
        p_hash = cls.compute_hash(payload)
        payload_str = json.dumps(payload, sort_keys=True)
        compressed_bytes = gzip.compress(payload_str.encode('utf-8'))

        import os
        project_id = os.environ.get("GCP_PROJECT_ID")
        credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

        if project_id and credentials_path:
            try:
                from google.cloud import storage
                client = storage.Client(project=project_id)
                bucket = client.bucket(bucket_name)
                blob = bucket.blob(f"audit_{p_hash}.json.gz")
                blob.upload_from_string(compressed_bytes, content_type="application/gzip")
            except Exception:
                pass
        return f"gs://{bucket_name}/audit_{p_hash}.json.gz"
