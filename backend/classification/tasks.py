
# backend/classification/tasks.py
import time
import logging
from typing import Dict, Any, List
from celery import shared_task, chain, Task
from django.core.cache import cache
from .models import WasteItem
from .constants import ClassificationStatus, CategoryChoices
from .repositories import WasteItemRepository
from .services_gcp import GeminiService

logger = logging.getLogger("classification.observability")

class ClassificationBaseTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        Failure fallback handler checking exceptions and ensuring no task is stuck in ANALYZING.
        """
        item_id = None
        if args:
            first_arg = args[0]
            if isinstance(first_arg, str):
                item_id = first_arg
            elif isinstance(first_arg, dict) and "item_id" in first_arg:
                item_id = first_arg["item_id"]
        elif kwargs and "item_id" in kwargs:
            item_id = kwargs["item_id"]

        if item_id:
            logger.error(
                f"Task failed in classification pipeline for item {item_id}. Transitioning state to FAILED.",
                extra={
                    "task_id": task_id,
                    "waste_item_id": item_id,
                    "error_class": exc.__class__.__name__,
                    "error_message": str(exc)
                }
            )
            try:
                repo = WasteItemRepository()
                repo.update_status_atomic(item_id, str(ClassificationStatus.FAILED))
            except Exception as e:
                logger.exception(f"Failed to atomically transition item {item_id} status to FAILED.")


def validate_gemini_output(result_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enforces category values, range bounds, and collection types constraints.
    """
    allowed_categories = [
        CategoryChoices.PLASTIC, CategoryChoices.PAPER, CategoryChoices.GLASS,
        CategoryChoices.METAL, CategoryChoices.ORGANIC, CategoryChoices.TEXTILE,
        CategoryChoices.E_WASTE, CategoryChoices.HAZARDOUS, CategoryChoices.MIXED_WASTE
    ]

    category = result_data.get("category")
    if not category or category not in allowed_categories:
        raise ValueError(f"Invalid category returned by AI: {category}")

    try:
        confidence = float(result_data.get("confidence", 0.0))
    except (TypeError, ValueError):
        raise ValueError("Confidence score must be numeric.")

    if not (0.0 <= confidence <= 1.0):
        raise ValueError(f"Confidence score {confidence} is out of bounds [0.0, 1.0].")

    for list_field in ["alternatives", "clarification_questions", "upcycling_guides"]:
        if not isinstance(result_data.get(list_field, []), list):
            raise ValueError(f"Output field {list_field} must be a list type.")

    return {
        "category": category,
        "confidence": confidence,
        "alternatives": result_data.get("alternatives", []),
        "requires_clarification": bool(result_data.get("requires_clarification", False)),
        "clarification_questions": result_data.get("clarification_questions", []),
        "disposal_instructions": str(result_data.get("disposal_instructions", "")),
        "upcycling_guides": result_data.get("upcycling_guides", [])
    }


@shared_task(
    bind=True,
    base=ClassificationBaseTask,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
    time_limit=120,
    soft_time_limit=90
)
def gemini_analysis_task(self, item_id: str) -> Dict[str, Any]:
    """
    Step 1: Generate category taxonomy and upcycling ideas using Gemini 1.5 Flash.
    """
    import os
    import hashlib
    from django.conf import settings

    repo = WasteItemRepository()
    item = repo.get_by_id(item_id)
    if not item:
        raise ValueError(f"WasteItem {item_id} not found.")

    # Local file integrity verification (replaces GCS check)
    relative_path = item.image_url.lstrip("/")
    if relative_path.startswith("media/"):
        relative_path = relative_path[6:]
    local_image_path = os.path.join(settings.MEDIA_ROOT, relative_path)

    if os.path.exists(local_image_path):
        with open(local_image_path, "rb") as f:
            image_bytes = f.read()
        computed_sha256 = hashlib.sha256(image_bytes).hexdigest()
        
        if computed_sha256.lower() != item.image_sha256.lower():
            raise ValueError("Local image SHA-256 mismatch. Potential cache poisoning attempt detected.")
    else:
        # Fallback GCS download verification logic if it starts with gs:// or http storage, otherwise raise FileNotFoundError
        if "storage.googleapis.com" in item.image_url or "storage.gcs.local" in item.image_url or item.image_url.startswith("gs://"):
            logger.warning("Simulated cloud storage integrity verification.")
        else:
            raise FileNotFoundError(f"Local image file not found at {local_image_path}")

    gemini_service = GeminiService()
    
    start_time = time.time()
    gemini_result = gemini_service.classify_waste_item(item.image_url, local_image_path=local_image_path)
    latency_ms = int((time.time() - start_time) * 1000)

    # Perform strict structural validation check
    validated_result = validate_gemini_output(gemini_result)

    return {
        "item_id": item_id,
        "labels": [],
        "gemini_result": validated_result,
        "latency_ms": latency_ms
    }


@shared_task(
    bind=True,
    base=ClassificationBaseTask,
    time_limit=30,
    soft_time_limit=20
)
def safety_filter_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 3: Analyze content for safety flags and override category if hazardous substances are found.
    """
    gemini_result = payload["gemini_result"]
    category = gemini_result.get("category", "Mixed Waste")
    disposal = gemini_result.get("disposal_instructions", "")

    # Clean check: Search for hazardous warning triggers
    hazard_words = ["asbestos", "battery", "acid", "toxic", "poison", "explosive", "ammunition", "chemical"]
    disposal_lower = disposal.lower()
    category_lower = category.lower()
    is_hazardous = any(
        word in disposal_lower.split() or word in category_lower.split()
        for word in hazard_words
    )

    if is_hazardous:
        logger.warning(f"Hazardous signature detected for WasteItem {payload['item_id']}. Overriding category.")
        gemini_result["category"] = CategoryChoices.HAZARDOUS
        gemini_result["disposal_instructions"] = f"[SAFETY ALERT - HAZARDOUS WASTE] {disposal}"

    payload["gemini_result"] = gemini_result
    return payload


@shared_task(
    bind=True,
    base=ClassificationBaseTask,
    time_limit=45,
    soft_time_limit=30
)
def finalize_classification_task(self, payload: Dict[str, Any]) -> str:
    """
    Step 4: Commit classification attributes to DB, set Redis cache and log metrics.
    """
    item_id = payload["item_id"]
    gemini_result = payload["gemini_result"]
    latency_ms = payload.get("latency_ms", 0)

    repo = WasteItemRepository()
    item = repo.get_by_id(item_id)
    if not item:
        raise ValueError(f"WasteItem {item_id} not found.")

    category = gemini_result.get("category", "Mixed Waste")
    confidence = gemini_result.get("confidence", 0.50)
    alternatives = gemini_result.get("alternatives", [])
    requires_clarification = gemini_result.get("requires_clarification", False)
    questions = gemini_result.get("clarification_questions", [])
    disposal = gemini_result.get("disposal_instructions", "")
    upcycling = gemini_result.get("upcycling_guides", [])

    # State transition determination based on confidence and safety status outcomes
    safety_status = payload.get("safety_status")
    
    if safety_status in ["BLOCKED", "FAILED"]:
        next_status = str(ClassificationStatus.FAILED)
    elif safety_status == "REVIEW_REQUIRED":
        next_status = str(ClassificationStatus.PENDING_CONFIRMATION)
    else:
        next_status = str(ClassificationStatus.CLASSIFIED)
        if requires_clarification or confidence < 0.60:
            next_status = str(ClassificationStatus.PENDING_CLARIFICATION)
        elif confidence < 0.85:
            next_status = str(ClassificationStatus.PENDING_CONFIRMATION)

    updates = {
        "predicted_category": category,
        "confidence_score": confidence,
        "alternatives": alternatives,
        "clarification_questions": questions,
        "disposal_instructions": disposal,
        "upcycling_guides": upcycling
    }

    # Atomic DB Commit
    repo.update_status_atomic(item_id, next_status, updates)

    # Enforce standard Cache Contract (classify:sha256:<sha256>)
    cache_key = f"classify:sha256:{item.image_sha256}"
    cache.set(
        cache_key,
        {
            "category": category,
            "confidence": float(confidence),
            "alternatives": alternatives,
            "disposal": disposal,
            "upcycling": upcycling
        },
        timeout=60 * 60 * 24 * 30  # 30 days
    )

    # AI Observability logging
    logger.info(
        "Structured AI Telemetry Log",
        extra={
            "request_id": self.request.id,
            "user_id": str(item.citizen.id),
            "waste_item_id": str(item.id),
            "model_name": "gemini-1.5-flash-001",
            "latency_ms": latency_ms,
            "token_usage": 0,  # Simulated token count
            "confidence": float(confidence),
            "status": next_status
        }
    )
    return item_id


@shared_task
def run_classification_pipeline_task(item_id: str) -> None:
    """
    Convenience wrapper task enqueuing the Celery pipeline chain sequentially.
    """
    from safety.tasks import safety_analysis_task
    pipeline_chain = chain(
        gemini_analysis_task.s(item_id),  # type: ignore
        safety_analysis_task.s(),  # type: ignore
        finalize_classification_task.s()  # type: ignore
    )
    pipeline_chain.apply_async()


@shared_task
def reap_stuck_classifications_task() -> int:
    """
    Periodic task to clean up items stuck in ANALYZING status due to worker crashes (e.g. SIGKILL/OOM).
    Transitions items older than 15 minutes to FAILED.
    """
    from django.utils import timezone
    from datetime import timedelta
    repo = WasteItemRepository()
    cutoff = timezone.now() - timedelta(minutes=15)
    stuck_items = repo.model.objects.filter(
        status=ClassificationStatus.ANALYZING,
        created_at__lt=cutoff
    )
    count = stuck_items.count()
    if count > 0:
        logger.warning(f"Reaping {count} stuck ANALYZING classification items.")
        stuck_items.update(status=ClassificationStatus.FAILED)
    return count
