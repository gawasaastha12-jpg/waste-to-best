# backend/safety/models.py
import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q, CheckConstraint
from classification.models import WasteItem
from .constants import RiskLevel, SafetyStatus, DecisionSource, ReviewPriority, ReviewStatus

class SafetyAssessment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    waste_item = models.OneToOneField(
        WasteItem,
        on_delete=models.CASCADE,
        related_name="safety_assessment",
        help_text="One-to-one mapping to the classification WasteItem."
    )
    status = models.CharField(
        max_length=32,
        choices=SafetyStatus.choices,
        default=SafetyStatus.PENDING,
        db_index=True
    )
    risk_level = models.CharField(
        max_length=32,
        choices=RiskLevel.choices,
        default=RiskLevel.SAFE,
        db_index=True
    )
    risk_score = models.FloatField(default=0.0)
    decision_source = models.CharField(
        max_length=32,
        choices=DecisionSource.choices,
        default=DecisionSource.AI_MODEL,
        db_index=True
    )
    hazard_categories = models.JSONField(default=list, blank=True)
    safety_flags = models.JSONField(default=list, blank=True)
    safe_disposal_method = models.TextField(blank=True, default="")
    approved_upcycling = models.JSONField(default=list, blank=True)
    blocked_upcycling = models.JSONField(default=list, blank=True)
    review_required = models.BooleanField(default=False)
    review_reason = models.TextField(blank=True, default="")
    rule_engine_version = models.CharField(max_length=32, default="1.0.0")
    model_version = models.CharField(max_length=64, default="gemini-1.5-flash")
    assessment_version = models.CharField(max_length=128, db_index=True, default="1.0.0:gemini-1.5-flash")
    processing_token = models.UUIDField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()

    class Meta:
        constraints = [
            CheckConstraint(
                check=Q(risk_score__gte=0.0) & Q(risk_score__lte=1.0),
                name="valid_risk_score"
            )
        ]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["risk_level", "created_at"]),
            models.Index(fields=["decision_source", "created_at"]),
            models.Index(fields=["processing_token"]),
        ]

    def __str__(self) -> str:
        return f"SafetyAssessment {self.id} - Status: {self.status} - Risk: {self.risk_level}"


class SafetyAuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    waste_item = models.ForeignKey(
        WasteItem,
        on_delete=models.PROTECT,
        related_name="safety_audit_logs",
        help_text="Immutable log entry representing audit trails."
    )
    payload_uri = models.CharField(max_length=512, help_text="URI pointing to the compressed GCS payload.")
    payload_hash = models.CharField(max_length=64, db_index=True)
    decision = models.CharField(max_length=64)
    reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = models.Manager()

    class Meta:
        indexes = [
            models.Index(fields=["payload_hash"]),
            models.Index(fields=["created_at"]),
        ]

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise ValidationError("SafetyAuditLog records are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs) -> None:
        raise ValidationError("SafetyAuditLog records are immutable and cannot be deleted.")

    def __str__(self) -> str:
        return f"SafetyAuditLog {self.id} - Decision: {self.decision}"


class ManualSafetyReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    waste_item = models.ForeignKey(
        WasteItem,
        on_delete=models.CASCADE,
        related_name="manual_safety_reviews"
    )
    assessment = models.ForeignKey(
        SafetyAssessment,
        on_delete=models.CASCADE,
        related_name="manual_reviews"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_safety_reviews"
    )
    status = models.CharField(
        max_length=32,
        choices=ReviewStatus.choices,
        default=ReviewStatus.OPEN
    )
    priority = models.CharField(
        max_length=32,
        choices=ReviewPriority.choices,
        default=ReviewPriority.MEDIUM
    )
    sla_due_at = models.DateTimeField()
    escalated_at = models.DateTimeField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()

    class Meta:
        indexes = [
            models.Index(fields=["status", "priority"]),
            models.Index(fields=["sla_due_at"]),
        ]

    def __str__(self) -> str:
        return f"ManualSafetyReview {self.id} - Status: {self.status} - Priority: {self.priority}"
