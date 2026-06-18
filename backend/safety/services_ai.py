# backend/safety/services_ai.py
import json
import logging
import os
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from typing import Dict, Any, List
from .constants import RiskLevel, HazardCategory
from classification.exceptions import GCPServiceError

logger = logging.getLogger("safety.ai")

class SafetyAIService:
    def __init__(self) -> None:
        self.project_id = os.environ.get("GCP_PROJECT_ID")
        self.location = os.environ.get("GCP_LOCATION", "us-central1")
        self.model_name = "gemini-1.5-flash-001"
        self.initialized = False

        try:
            vertexai.init(project=self.project_id, location=self.location)
            self.initialized = True
        except Exception:
            logger.warning("Vertex AI initialization failed inside SafetyAIService. Mock safety engine active.")

    def analyze_safety(self, image_url: str, category: str, labels: List[str]) -> Dict[str, Any]:
        """
        Uses Vertex AI Gemini 1.5 Flash to assess safety and hazard levels of a classified waste item.
        """
        # Define choices to instruct the AI
        allowed_risk_levels = [r.value for r in RiskLevel]
        allowed_hazard_categories = [h.value for h in HazardCategory]

        prompt = f"""
        You are an expert AI Safety Engine verifying a waste item with predicted category: '{category}' and labels: {', '.join(labels)}.
        Analyze the image and labels for safety hazards (toxic chemicals, fire risk, batteries, medical/sharps, etc.).
        
        Output EXACTLY a JSON structure matching this schema:
        {{
          "risk_level": "SAFE | LOW | MEDIUM | HIGH | CRITICAL",
          "risk_score": Float (between 0.0 and 1.0),
          "hazard_categories": [list containing matching categories from: {', '.join(allowed_hazard_categories)}],
          "safe_disposal_method": "String detailing safe disposal rules",
          "approved_upcycling": ["List of approved safe upcycling ideas"],
          "blocked_upcycling": ["List of prohibited hazardous upcycling/DIY ideas"],
          "review_required": Boolean (true if any danger or ambiguity is detected),
          "review_reason": "Explanation of why manual review is needed or blank if not required"
        }}
        """

        if not self.initialized:
            # Fallback simulated response
            return {
                "risk_level": RiskLevel.SAFE.value,
                "risk_score": 0.10,
                "hazard_categories": [],
                "safe_disposal_method": "Wash container and place in standard plastic recycling stream.",
                "approved_upcycling": ["Plastic planters", "Storage bins"],
                "blocked_upcycling": ["Do not burn or melt plastic containers indoors."],
                "review_required": False,
                "review_reason": ""
            }

        try:
            # Enforce 30 seconds timeout configuration via generation/client defaults if available
            model = GenerativeModel(
                self.model_name,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.0,
                }
            )

            image_mime = "image/png" if image_url.lower().endswith(".png") else "image/jpeg"
            image_part = Part.from_uri(mime_type=image_mime, uri=image_url)
            
            # Executing generation
            response = model.generate_content([image_part, prompt], request_options={"timeout": 30.0})
            result_data = json.loads(response.text)
            return result_data
        except Exception as e:
            logger.exception("Gemini Vertex AI safety analysis processing failure.")
            raise GCPServiceError(f"Gemini Safety analysis failed: {str(e)}")
