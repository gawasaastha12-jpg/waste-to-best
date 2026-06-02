# backend/classification/models.py
import uuid
from django.db import models
from django.conf import settings
from .constants import CategoryChoices, ClassificationStatus

class WasteItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    citizen = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='waste_items'
    )
    image_url = models.URLField(max_length=512)
    image_sha256 = models.CharField(max_length=64, db_index=True)
    status = models.CharField(
        max_length=30,
        choices=ClassificationStatus.choices,
        default=ClassificationStatus.ANALYZING,
        db_index=True
    )
    predicted_category = models.CharField(
        max_length=50,
        choices=CategoryChoices.choices,
        blank=True,
        null=True,
        db_index=True
    )
    confidence_score = models.DecimalField(
        max_length=5,
        max_digits=5,
        decimal_places=4,
        blank=True,
        null=True,
        db_index=True
    )
    alternatives = models.JSONField(default=list, blank=True)
    clarification_questions = models.JSONField(default=list, blank=True)
    disposal_instructions = models.TextField(blank=True, null=True)
    upcycling_guides = models.JSONField(default=list, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['citizen', 'status']),
            models.Index(fields=['image_sha256', 'status']),
        ]

    def __str__(self) -> str:
        return f"WasteItem {self.id} - {self.status}"
