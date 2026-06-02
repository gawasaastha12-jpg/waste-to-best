# backend/classification/services.py
import hashlib
import uuid
import logging
from typing import Dict, Any, Optional
from django.core.cache import cache
from django.conf import settings
from .models import WasteItem
from .constants import ClassificationStatus
from .repositories import WasteItemRepository
from .services_gcp import GCSService
from .tasks import run_classification_pipeline_task

logger = logging.getLogger("classification.service")

CACHE_TTL = 60 * 60 * 24 * 30  # 30 days

class ImageUploadService:
    def __init__(self) -> None:
        self.gcs_service = GCSService()

    def request_signed_upload(self, file_name: str, file_size: int, content_type: str) -> Dict[str, Any]:
        """
        Coordinates generating GCS signed upload URLs for frontend image placement.
        """
        # Enforce unique blob names using UUIDs
        ext = file_name.split('.')[-1]
        unique_name = f"{uuid.uuid4()}.{ext}"
        
        signed_url = self.gcs_service.generate_signed_upload_url(unique_name)
        gcs_base = f"https://storage.googleapis.com/{self.gcs_service.bucket_name}"
        if not signed_url.startswith("https://storage.googleapis.com"):
            gcs_base = f"https://storage.gcs.local/{self.gcs_service.bucket_name}"

        return {
            "signed_url": signed_url,
            "image_url": f"{gcs_base}/{unique_name}",
            "file_name": unique_name
        }


class ClassificationPipelineService:
    def __init__(self) -> None:
        self.repository = WasteItemRepository()

    def submit_classification(self, citizen: Any, image_url: str, sha256: str) -> WasteItem:
        """
        Submits an image for classification. First checks the cache, falling back to 
        scheduling the asynchronous Celery pipeline if not found.
        """
        # Validate SHA-256 signature format to protect against cache anomalies
        if len(sha256) != 64 or not all(c in "0123456789abcdefABCDEF" for c in sha256):
            raise ValueError("Invalid image SHA-256 signature.")

        # Cost Protection: Enforce daily classification quota limit (Max 50 items/day)
        from django.utils import timezone
        yesterday = timezone.now() - timezone.timedelta(days=1)
        daily_count = self.repository.model.objects.filter(
            citizen=citizen,
            created_at__gte=yesterday
        ).count()
        if daily_count >= 50:
            raise PermissionError("Daily classification quota limit of 50 items exceeded.")

        cache_key = f"classify:sha256:{sha256.lower()}"
        cached_data = cache.get(cache_key)

        if cached_data:
            logger.info(f"Cache hit on SHA256 {sha256}. Bypassing AI pipeline.")
            # Reuse classification results
            return self.repository.create(
                citizen=citizen,
                image_url=image_url,
                image_sha256=sha256.lower(),
                status=ClassificationStatus.CLASSIFIED,
                predicted_category=cached_data.get("category"),
                confidence_score=cached_data.get("confidence"),
                alternatives=cached_data.get("alternatives", []),
                disposal_instructions=cached_data.get("disposal", ""),
                upcycling_guides=cached_data.get("upcycling", [])
            )

        # Cache miss: Create standard WasteItem record with ANALYZING state
        waste_item = self.repository.create(
            citizen=citizen,
            image_url=image_url,
            image_sha256=sha256.lower(),
            status=ClassificationStatus.ANALYZING
        )

        # Enqueue background Celery task
        run_classification_pipeline_task.delay(str(waste_item.id))
        return waste_item

    def confirm_classification(self, user: Any, item_id: str, confirmed_category: str) -> WasteItem:
        """
        Allows the citizen to verify or override the category classification.
        """
        item = self.repository.get_by_id(item_id)
        if not item:
            raise ValueError("Waste item not found.")
        
        # Verify object ownership
        if item.citizen != user:
            raise PermissionError("Access denied.")

        updates = {"predicted_category": confirmed_category}
        return self.repository.update_status_atomic(
            item_id=str(item.id),
            status=ClassificationStatus.CLASSIFIED,
            updates=updates
        )
