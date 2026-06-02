# backend/safety/serializers.py
from rest_framework import serializers
from .models import SafetyAssessment, ManualSafetyReview, SafetyAuditLog

class SafetyAssessmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SafetyAssessment
        fields = [
            "id", "waste_item", "status", "risk_level", "risk_score",
            "decision_source", "hazard_categories", "safety_flags",
            "safe_disposal_method", "approved_upcycling", "blocked_upcycling",
            "review_required", "review_reason", "rule_engine_version",
            "model_version", "assessment_version", "created_at", "updated_at"
        ]
        read_only_fields = fields


class ManualSafetyReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = ManualSafetyReview
        fields = [
            "id", "waste_item", "assessment", "assigned_to", "status",
            "priority", "sla_due_at", "escalated_at", "claimed_at",
            "review_notes", "created_at", "resolved_at"
        ]
        read_only_fields = fields


class ClaimReviewSerializer(serializers.Serializer):
    review_id = serializers.UUIDField()


class ResolveReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["APPROVED", "BLOCKED"])
    review_notes = serializers.CharField(max_length=2000, required=True)
