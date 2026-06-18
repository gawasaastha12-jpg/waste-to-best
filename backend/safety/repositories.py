# backend/safety/repositories.py
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import SafetyAssessment, SafetyAuditLog, ManualSafetyReview
from .constants import SafetyStatus, ReviewStatus

class SafetyStateMachine:
    ALLOWED_TRANSITIONS = {
        SafetyStatus.PENDING: {SafetyStatus.ANALYZING, SafetyStatus.FAILED},
        SafetyStatus.ANALYZING: {
            SafetyStatus.APPROVED,
            SafetyStatus.BLOCKED,
            SafetyStatus.REVIEW_REQUIRED,
            SafetyStatus.FAILED
        },
        SafetyStatus.REVIEW_REQUIRED: {
            SafetyStatus.APPROVED,
            SafetyStatus.BLOCKED,
            SafetyStatus.FAILED
        }
    }

    @classmethod
    def validate_transition(cls, old_status: str, new_status: str) -> None:
        if old_status == new_status:
            return
        allowed = cls.ALLOWED_TRANSITIONS.get(old_status, set())
        if new_status not in allowed:
            raise ValidationError(
                f"State transition error: safety status cannot transition from {old_status} to {new_status}."
            )


class SafetyRepository:
    def get_by_id(self, assessment_id: str) -> SafetyAssessment:
        return SafetyAssessment.objects.filter(pk=assessment_id).first()

    def get_by_waste_item_id(self, waste_item_id: str) -> SafetyAssessment:
        return SafetyAssessment.objects.filter(waste_item_id=waste_item_id).first()

    def get_or_create_assessment(self, waste_item_id: str) -> SafetyAssessment:
        with transaction.atomic():
            assessment, created = SafetyAssessment.objects.get_or_create(
                waste_item_id=waste_item_id,
                defaults={
                    "status": SafetyStatus.PENDING,
                    "assessment_version": "1.0.0:gemini-1.5-flash"
                }
            )
            return assessment

    def transition_status(self, assessment_id: str, new_status: str, updates: dict = None) -> SafetyAssessment:
        """
        Transition status with database-safe state machine enforcement and row-level locking.
        """
        with transaction.atomic():
            assessment = SafetyAssessment.objects.select_for_update().get(pk=assessment_id)
            old_status = assessment.status
            
            # State Machine Check
            SafetyStateMachine.validate_transition(old_status, new_status)
            
            assessment.status = new_status
            if updates:
                for key, val in updates.items():
                    if hasattr(assessment, key):
                        setattr(assessment, key, val)
            
            assessment.save()
            return assessment

    def create_audit_log(self, waste_item_id: str, payload_uri: str, payload_hash: str, decision: str, reason: str) -> SafetyAuditLog:
        return SafetyAuditLog.objects.create(
            waste_item_id=waste_item_id,
            payload_uri=payload_uri,
            payload_hash=payload_hash,
            decision=decision,
            reason=reason
        )

    def create_manual_review(self, waste_item_id: str, assessment_id: str, priority: str, sla_duration_hours: int = 24) -> ManualSafetyReview:
        from datetime import timedelta
        sla_due_at = timezone.now() + timedelta(hours=sla_duration_hours)
        return ManualSafetyReview.objects.create(
            waste_item_id=waste_item_id,
            assessment_id=assessment_id,
            priority=priority,
            status=ReviewStatus.OPEN,
            sla_due_at=sla_due_at
        )

    def claim_review(self, review_id: str, reviewer) -> ManualSafetyReview:
        """
        Claims a manual review atomically inside a transaction with skip_locked=True.
        """
        with transaction.atomic():
            reviews = ManualSafetyReview.objects.select_for_update(skip_locked=True).filter(
                pk=review_id,
                status=ReviewStatus.OPEN
            )
            review = reviews.first()
            if not review:
                raise ValidationError("Review is not open or is currently locked/claimed by another user.")
            
            review.assigned_to = reviewer
            review.claimed_at = timezone.now()
            review.status = ReviewStatus.IN_PROGRESS
            review.save()
            return review

    def resolve_review(self, review_id: str, notes: str, decision: str) -> ManualSafetyReview:
        with transaction.atomic():
            review = ManualSafetyReview.objects.select_for_update().get(pk=review_id)
            review.review_notes = notes
            review.resolved_at = timezone.now()
            review.status = ReviewStatus.RESOLVED if decision == "APPROVED" else ReviewStatus.REJECTED
            review.save()
            return review
