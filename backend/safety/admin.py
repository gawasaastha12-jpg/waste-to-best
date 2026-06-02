# backend/safety/admin.py
from django.contrib import admin
from .models import SafetyAssessment, SafetyAuditLog, ManualSafetyReview

@admin.register(SafetyAssessment)
class SafetyAssessmentAdmin(admin.ModelAdmin):
    list_display = ("id", "waste_item", "status", "risk_level", "risk_score", "decision_source", "created_at")
    list_filter = ("status", "risk_level", "decision_source")
    search_fields = ("id", "waste_item__id")
    readonly_fields = ("created_at", "updated_at")


@admin.register(SafetyAuditLog)
class SafetyAuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "waste_item", "payload_uri", "payload_hash", "decision", "created_at")
    list_filter = ("decision", "created_at")
    search_fields = ("waste_item__id", "payload_hash")

    # Enforce read-only for logs
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ManualSafetyReview)
class ManualSafetyReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "waste_item", "status", "priority", "assigned_to", "sla_due_at", "created_at")
    list_filter = ("status", "priority", "created_at")
    search_fields = ("id", "waste_item__id", "review_notes")
