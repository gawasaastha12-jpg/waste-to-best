# backend/safety/tasks.py
import logging
import uuid
import time
from typing import Dict, Any
from celery import shared_task, Task
from django.core.cache import cache
from django.utils import timezone
from django.db import transaction

from classification.models import WasteItem
from classification.repositories import WasteItemRepository
from classification.constants import ClassificationStatus

from .models import SafetyAssessment
from .constants import SafetyStatus, RiskLevel, DecisionSource, HazardCategory, ReviewPriority, RULE_ENGINE_VERSION, MIN_SAFETY_CONFIDENCE
from .repositories import SafetyRepository
from .services import VersionedRuleEngine, validate_safety_output, AuditGCSService
from .services_ai import SafetyAIService

logger = logging.getLogger("safety.tasks")

class SafetyBaseTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        Transition assessment and classification status to FAILED on unhandled exceptions.
        """
        logger.error(f"Safety Task {task_id} failed: {str(exc)}")
        if args:
            payload = args[0]
            if isinstance(payload, dict) and "item_id" in payload:
                item_id = payload["item_id"]
                try:
                    repo = SafetyRepository()
                    assessment = repo.get_by_waste_item_id(item_id)
                    if assessment:
                        repo.transition_status(assessment.id, SafetyStatus.FAILED)
                    # Mark classification as failed
                    WasteItemRepository().update_status_atomic(
                        item_id,
                        ClassificationStatus.FAILED,
                        {"disposal_instructions": f"[SAFETY ENGINE FAILURE] Safety pipeline aborted: {str(exc)}"}
                    )
                except Exception as e:
                    logger.exception(f"Fallback failure recovery failed for item {item_id}: {str(e)}")


def check_and_update_circuit_breaker(success: bool = True) -> bool:
    """
    Circuit Breaker logic: switches to deterministic rules if error rate exceeds 20% in 5 minutes.
    """
    now = time.time()
    success_key = "safety:cb:success_count"
    failure_key = "safety:cb:failure_count"
    block_key = "safety:cb:blocked_until"

    blocked_until = cache.get(block_key)
    if blocked_until and now < float(blocked_until):
        # Circuit is open (tripped)
        return False

    # Increment metric counts
    if success:
        cache.incr(success_key, 1) if cache.get(success_key) is not None else cache.set(success_key, 1, timeout=300)
    else:
        cache.incr(failure_key, 1) if cache.get(failure_key) is not None else cache.set(failure_key, 1, timeout=300)

    # Compute error rate
    successes = float(cache.get(success_key) or 0)
    failures = float(cache.get(failure_key) or 0)
    total = successes + failures

    if total >= 10:  # Minimum request volume before tripping
        error_rate = failures / total
        if error_rate > 0.20:
            logger.critical(f"Gemini Safety circuit breaker tripped! Error rate: {error_rate:.2%}. Fallback active.")
            cache.set(block_key, now + 900, timeout=900)  # Trip for 15 minutes
            return False

    return True


@shared_task(
    bind=True,
    base=SafetyBaseTask,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
    time_limit=120,
    soft_time_limit=90
)
def safety_analysis_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 3 of the Classification Pipeline: Process safety rule engines, structured AI prompts,
    idempotent check protections, cache stampede prevention and blockchain audit logging.
    """
    item_id = payload["item_id"]
    labels = payload.get("labels", [])
    gemini_result = payload.get("gemini_result", {})
    category = gemini_result.get("category", "Mixed Waste")

    # Fetch corresponding database records
    waste_repo = WasteItemRepository()
    item = waste_repo.get_by_id(item_id)
    if not item:
        raise ValueError(f"WasteItem {item_id} not found.")

    safety_repo = SafetyRepository()
    assessment = safety_repo.get_or_create_assessment(item_id)

    # 1. Assessment Idempotency Protection
    if assessment.status in [SafetyStatus.APPROVED, SafetyStatus.BLOCKED, SafetyStatus.REVIEW_REQUIRED]:
        logger.info(f"Safety assessment for item {item_id} already finalized with status: {assessment.status}")
        payload["safety_status"] = assessment.status
        return payload

    # Enforce ANALYZING transition
    assessment = safety_repo.transition_status(assessment.id, SafetyStatus.ANALYZING)

    # Cache keys
    model_version = "gemini-1.5-flash-001"
    cache_key = f"safety:{RULE_ENGINE_VERSION}:{model_version}:sha256:{item.image_sha256}"
    lock_key = f"safety-lock:{item.image_sha256}"
    token = str(uuid.uuid4())

    # 2. Versioned Cache Lookup
    cached_data = cache.get(cache_key)
    if cached_data:
        # Cache Integrity Check
        if cached_data.get("assessment_version") == assessment.assessment_version:
            logger.info(f"Cache hit for safety evaluation of item {item_id}.")
            result = cached_data["result"]
            
            # Apply cached results
            updates = {
                "risk_level": result["risk_level"],
                "risk_score": result["risk_score"],
                "decision_source": result["decision_source"],
                "hazard_categories": result["hazard_categories"],
                "safety_flags": result.get("safety_flags", []),
                "safe_disposal_method": result["safe_disposal_method"],
                "approved_upcycling": result["approved_upcycling"],
                "blocked_upcycling": result["blocked_upcycling"],
                "review_required": result["review_required"],
                "review_reason": result["review_reason"],
            }
            final_status = result["status"]
            safety_repo.transition_status(assessment.id, final_status, updates)
            payload["safety_status"] = final_status
            return payload

    # 3. Cache Stampede Lock Acquisition
    acquired = cache.add(lock_key, token, timeout=300)
    if not acquired:
        logger.warning(f"Cache stampede lock active for item {item_id}. Retrying task.")
        raise self.retry(countdown=5)

    try:
        decision_source = DecisionSource.AI_MODEL
        safety_data = None

        # 4. Deterministic Rule Engine Evaluation
        rule_result = VersionedRuleEngine.evaluate(category, labels)
        if rule_result:
            logger.info(f"Deterministic Safety Rule triggered for item {item_id}.")
            safety_data = rule_result
            decision_source = DecisionSource.RULE_OVERRIDE if category == "Hazardous" else DecisionSource.RULE_ENGINE
        else:
            # 5. Safety AIService Analysis (Circuit Breaker Safe)
            cb_active = check_and_update_circuit_breaker(success=True)
            if cb_active:
                try:
                    ai_service = SafetyAIService()
                    ai_result = ai_service.analyze_safety(item.image_url, category, labels)
                    
                    # AI Validation Checks
                    validate_safety_output(ai_result)
                    safety_data = ai_result
                    
                    # Update success metric
                    check_and_update_circuit_breaker(success=True)
                except Exception as ex:
                    logger.error(f"Vertex AI Safety service failure: {str(ex)}")
                    check_and_update_circuit_breaker(success=False)
                    # Trigger retry or fallback
                    raise

            # Fallback to rule engine / manual review when circuit breaker is tripped
            if not safety_data:
                logger.warning(f"Safety circuit breaker fallback triggered for item {item_id}.")
                safety_data = {
                    "risk_level": RiskLevel.HIGH.value,
                    "risk_score": 0.85,
                    "hazard_categories": [HazardCategory.UNKNOWN.value],
                    "safe_disposal_method": "System running in safety-lock fallback mode. Refrain from touching until verified.",
                    "approved_upcycling": [],
                    "blocked_upcycling": ["All upcycling ideas blocked during emergency fallback mode."],
                    "review_required": True,
                    "review_reason": "Gemini safety service offline. Reverted to safety fallback queue."
                }
                decision_source = DecisionSource.RULE_ENGINE

        # 6. Safety Confidence Level Check
        risk_score = float(safety_data.get("risk_score", 0.0))
        if risk_score > 0.0 and risk_score < MIN_SAFETY_CONFIDENCE:
            logger.warning(f"Safety score {risk_score} is below confidence threshold {MIN_SAFETY_CONFIDENCE}. Forcing manual review.")
            safety_data["review_required"] = True
            safety_data["review_reason"] = f"AI risk confidence ({risk_score}) below safety limit."

        # Merge fields and finalize decision status
        review_required = safety_data.get("review_required", False)
        risk_level = safety_data.get("risk_level", RiskLevel.SAFE.value)

        final_status = SafetyStatus.APPROVED
        if review_required:
            final_status = SafetyStatus.REVIEW_REQUIRED
        elif risk_level in [RiskLevel.HIGH.value, RiskLevel.CRITICAL.value]:
            final_status = SafetyStatus.BLOCKED

        updates = {
            "risk_level": risk_level,
            "risk_score": risk_score,
            "decision_source": decision_source,
            "hazard_categories": safety_data.get("hazard_categories", []),
            "safety_flags": safety_data.get("safety_flags", []),
            "safe_disposal_method": safety_data.get("safe_disposal_method", ""),
            "approved_upcycling": safety_data.get("approved_upcycling", []),
            "blocked_upcycling": safety_data.get("blocked_upcycling", []),
            "review_required": review_required,
            "review_reason": safety_data.get("review_reason", ""),
            "rule_engine_version": RULE_ENGINE_VERSION,
            "model_version": model_version,
            "assessment_version": f"{RULE_ENGINE_VERSION}:{model_version}"
        }

        # Transactional transition commit
        safety_repo.transition_status(assessment.id, final_status, updates)

        # 7. Audit Logging GCS offload
        audit_payload = {
            "input_labels": labels,
            "classification_category": category,
            "safety_result": safety_data,
            "decision_source": decision_source
        }
        payload_uri = AuditGCSService.upload_to_gcs(audit_payload)
        payload_hash = AuditGCSService.compute_hash(audit_payload)

        # Create immutable Audit record
        safety_repo.create_audit_log(
            waste_item_id=item_id,
            payload_uri=payload_uri,
            payload_hash=payload_hash,
            decision=final_status,
            reason=safety_data.get("review_reason", "")
        )

        # 8. Create Manual Safety Review queue entry
        if final_status == SafetyStatus.REVIEW_REQUIRED:
            priority = ReviewPriority.MEDIUM
            if risk_level == RiskLevel.CRITICAL.value:
                priority = ReviewPriority.CRITICAL
            elif risk_level == RiskLevel.HIGH.value:
                priority = ReviewPriority.HIGH

            safety_repo.create_manual_review(
                waste_item_id=item_id,
                assessment_id=assessment.id,
                priority=priority
            )

        # 9. Populate the standard Cache Contract
        cache.set(
            cache_key,
            {
                "assessment_version": f"{RULE_ENGINE_VERSION}:{model_version}",
                "result": {
                    "status": final_status,
                    "risk_level": risk_level,
                    "risk_score": risk_score,
                    "decision_source": decision_source,
                    "hazard_categories": safety_data.get("hazard_categories", []),
                    "safety_flags": safety_data.get("safety_flags", []),
                    "safe_disposal_method": safety_data.get("safe_disposal_method", ""),
                    "approved_upcycling": safety_data.get("approved_upcycling", []),
                    "blocked_upcycling": safety_data.get("blocked_upcycling", []),
                    "review_required": review_required,
                    "review_reason": safety_data.get("review_reason", "")
                }
            },
            timeout=60 * 60 * 24 * 30  # 30 days
        )

        payload["safety_status"] = final_status
        return payload

    finally:
        # Secure lua-style stampede lock release verification
        try:
            if cache.get(lock_key) == token:
                cache.delete(lock_key)
        except Exception:
            pass


@shared_task
def reap_stuck_safety_tasks() -> int:
    """
    Cleans up safety tasks stuck in ANALYZING for > 15 minutes or PENDING for > 30 minutes.
    """
    now = timezone.now()
    repo = SafetyRepository()
    
    # 1. ANALYZING reaper cutoff
    analyzing_cutoff = now - timezone.timedelta(minutes=15)
    stuck_analyzing = SafetyAssessment.objects.filter(
        status=SafetyStatus.ANALYZING,
        updated_at__lt=analyzing_cutoff
    )
    count = 0
    for assess in stuck_analyzing:
        repo.transition_status(assess.id, SafetyStatus.FAILED)
        WasteItemRepository().update_status_atomic(
            assess.waste_item.id,
            ClassificationStatus.FAILED,
            {"disposal_instructions": "[SAFETY REAPER TIMEOUT] Safety analysis task timed out."}
        )
        count += 1

    # 2. PENDING reaper cutoff
    pending_cutoff = now - timezone.timedelta(minutes=30)
    stuck_pending = SafetyAssessment.objects.filter(
        status=SafetyStatus.PENDING,
        created_at__lt=pending_cutoff
    )
    for assess in stuck_pending:
        repo.transition_status(assess.id, SafetyStatus.FAILED)
        WasteItemRepository().update_status_atomic(
            assess.waste_item.id,
            ClassificationStatus.FAILED,
            {"disposal_instructions": "[SAFETY REAPER TIMEOUT] Safety analysis enqueuing timed out."}
        )
        count += 1

    return count


@shared_task
def escalate_overdue_reviews_task() -> int:
    """
    Finds open manual reviews past SLA and bumps their priority.
    """
    from .models import ManualSafetyReview
    now = timezone.now()
    overdue_reviews = ManualSafetyReview.objects.filter(
        status=ReviewStatus.OPEN,
        sla_due_at__lt=now
    )
    
    count = 0
    for review in overdue_reviews:
        old_priority = review.priority
        if review.priority == ReviewPriority.LOW:
            review.priority = ReviewPriority.MEDIUM
        elif review.priority == ReviewPriority.MEDIUM:
            review.priority = ReviewPriority.HIGH
        elif review.priority == ReviewPriority.HIGH:
            review.priority = ReviewPriority.CRITICAL

        review.escalated_at = now
        review.save()
        logger.warning(
            f"Escalated manual review {review.id} for WasteItem {review.waste_item.id} due to SLA breach. "
            f"Priority bumped from {old_priority} to {review.priority}."
        )
        count += 1
    return count
