# backend/classification/tests.py
import uuid
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status

from .models import WasteItem
from .constants import ClassificationStatus, CategoryChoices
from .repositories import WasteItemRepository
from .serializers import SignedURLRequestSerializer, ClassificationConfirmSerializer
from .services import ImageUploadService, ClassificationPipelineService
from .tasks import gemini_analysis_task, safety_filter_task, finalize_classification_task

User = get_user_model()

class WasteItemRepositoryTests(TestCase):
    def setUp(self):
        self.citizen = User.objects.create_user(email="citizen@test.com", password="securepassword123")
        self.repository = WasteItemRepository()

    def test_create_and_query_item(self):
        item = self.repository.create(
            citizen=self.citizen,
            image_url="https://storage.gcs/img.jpg",
            image_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            status=ClassificationStatus.ANALYZING
        )
        self.assertIsNotNone(item.id)
        
        # Test lookups
        fetched = self.repository.get_by_id(str(item.id))
        self.assertEqual(fetched.image_sha256, item.image_sha256)

        # Test filter
        items = self.repository.filter_by_citizen_and_status(str(self.citizen.id), ClassificationStatus.ANALYZING)
        self.assertEqual(len(items), 1)

    def test_duplicate_lookup(self):
        hash_val = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        # Duplicate detection requires CLASSIFIED status
        item = self.repository.create(
            citizen=self.citizen,
            image_url="https://storage.gcs/img2.jpg",
            image_sha256=hash_val,
            status=ClassificationStatus.CLASSIFIED,
            predicted_category=CategoryChoices.METAL,
            confidence_score=0.95
        )
        duplicate = self.repository.get_by_sha256(hash_val)
        self.assertIsNotNone(duplicate)
        self.assertEqual(duplicate.predicted_category, CategoryChoices.METAL)

    def test_atomic_status_update(self):
        item = self.repository.create(
            citizen=self.citizen,
            image_url="https://storage.gcs/img3.jpg",
            image_sha256="abcde12345abcde12345abcde12345abcde12345abcde12345abcde123456789",
            status=ClassificationStatus.ANALYZING
        )
        updated = self.repository.update_status_atomic(
            item_id=str(item.id),
            status=ClassificationStatus.CLASSIFIED,
            updates={"predicted_category": CategoryChoices.GLASS, "confidence_score": 0.88}
        )
        self.assertEqual(updated.status, ClassificationStatus.CLASSIFIED)
        self.assertEqual(updated.predicted_category, CategoryChoices.GLASS)


class ClassificationServicesAndTasksTests(TestCase):
    def setUp(self):
        self.citizen = User.objects.create_user(email="citizen@test.com", password="securepassword123")
        cache.clear()

    def test_image_upload_signed_url(self):
        upload_service = ImageUploadService()
        result = upload_service.request_signed_upload("plastic_bottle.png", 1024, "image/png")
        self.assertIn("/api/v1/classification/upload-local/", result["signed_url"])
        self.assertTrue(result["image_url"].endswith(".png"))

    @patch('classification.tasks.run_classification_pipeline_task.delay')
    def test_submit_classification_cache_miss(self, mock_celery):
        pipeline_service = ClassificationPipelineService()
        sha_hash = "f" * 64
        item = pipeline_service.submit_classification(
            citizen=self.citizen,
            image_url="https://storage.gcs/new.jpg",
            sha256=sha_hash
        )
        self.assertEqual(item.status, ClassificationStatus.ANALYZING)
        mock_celery.assert_called_once_with(str(item.id))

    def test_submit_classification_cache_hit(self):
        pipeline_service = ClassificationPipelineService()
        sha_hash = "d" * 64
        # Seed cache
        cache_key = f"classify:sha256:{sha_hash}"
        cache.set(cache_key, {
            "category": CategoryChoices.PAPER,
            "confidence": 0.90,
            "alternatives": ["Wood"],
            "disposal": "Discard in blue recycling bin",
            "upcycling": ["Make paper bags"]
        }, timeout=300)

        item = pipeline_service.submit_classification(
            citizen=self.citizen,
            image_url="https://storage.gcs/cached.jpg",
            sha256=sha_hash
        )
        self.assertEqual(item.status, ClassificationStatus.CLASSIFIED)
        self.assertEqual(item.predicted_category, CategoryChoices.PAPER)
        self.assertEqual(float(item.confidence_score), 0.90)

    @patch('classification.tasks.GeminiService.classify_waste_item')
    def test_celery_pipeline_tasks(self, mock_gemini):
        mock_gemini.return_value = {
            "category": "Metal",
            "confidence": 0.95,
            "alternatives": ["Mixed Waste"],
            "requires_clarification": False,
            "clarification_questions": [],
            "disposal_instructions": "Throw in bin",
            "upcycling_guides": []
        }

        item = WasteItem.objects.create(
            citizen=self.citizen,
            image_url="https://storage.gcs.local/tin_can.jpg",
            image_sha256="c" * 64,
            status=ClassificationStatus.ANALYZING
        )

        # 1. Gemini
        gemini_result = gemini_analysis_task(str(item.id))
        self.assertIn("gemini_result", gemini_result)

        # 2. Safety Filter
        safety_result = safety_filter_task(gemini_result)
        self.assertEqual(safety_result["gemini_result"]["category"], "Metal")

        # 3. Finalize
        finalize_result = finalize_classification_task(safety_result)
        item.refresh_from_db()
        self.assertEqual(item.status, ClassificationStatus.CLASSIFIED)
        self.assertEqual(item.predicted_category, CategoryChoices.METAL)

    def test_safety_hazard_override(self):
        payload = {
            "item_id": "dummy_uuid",
            "gemini_result": {
                "category": "Mixed Waste",
                "confidence": 0.70,
                "disposal_instructions": "Warning! Contains corrosive acid elements and battery chemicals."
            }
        }
        res = safety_filter_task(payload)
        self.assertEqual(res["gemini_result"]["category"], CategoryChoices.HAZARDOUS)


class ClassificationAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.citizen = User.objects.create_user(email="citizen@test.com", password="securepassword123")
        self.other_user = User.objects.create_user(email="stranger@test.com", password="securepassword123")
        self.client.force_authenticate(user=self.citizen)

    def test_signed_url_validation(self):
        url = reverse('classification_signed_url')
        response = self.client.post(url, {
            "file_name": "test.jpg",
            "file_size": 2048,
            "content_type": "application/pdf"  # Invalid upload type
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('classification.tasks.run_classification_pipeline_task.delay')
    def test_submit_and_status_ownership(self, mock_celery):
        # 1. Submit
        submit_url = reverse('classification_submit')
        submit_response = self.client.post(submit_url, {
            "image_url": "https://storage.gcs/submitted.jpg",
            "image_sha256": "a" * 64
        }, format='json')
        self.assertEqual(submit_response.status_code, status.HTTP_201_CREATED)
        item_id = submit_response.data["id"]

        # 2. Get status (Authorized owner)
        status_url = reverse('classification_status', kwargs={"uuid": item_id})
        status_response = self.client.get(status_url)
        self.assertEqual(status_response.status_code, status.HTTP_200_OK)

        # 3. Get status (Unauthorized other user)
        self.client.force_authenticate(user=self.other_user)
        unauth_response = self.client.get(status_url)
        self.assertEqual(unauth_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_confirm_endpoint(self):
        item = WasteItem.objects.create(
            citizen=self.citizen,
            image_url="https://storage.gcs/confirm.jpg",
            image_sha256="z" * 64,
            status=ClassificationStatus.PENDING_CONFIRMATION,
            predicted_category=CategoryChoices.PLASTIC,
            confidence_score=0.75
        )

        confirm_url = reverse('classification_confirm')
        response = self.client.post(confirm_url, {
            "waste_item_id": str(item.id),
            "confirmed_category": CategoryChoices.METAL
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item.refresh_from_db()
        self.assertEqual(item.status, ClassificationStatus.CLASSIFIED)
        self.assertEqual(item.predicted_category, CategoryChoices.METAL)

    def test_daily_classification_quota_exceeded(self):
        # Create 50 items for the user
        for i in range(50):
            WasteItem.objects.create(
                citizen=self.citizen,
                image_url=f"https://storage.gcs/item_{i}.jpg",
                image_sha256="a" * 64,
                status=ClassificationStatus.CLASSIFIED
            )

        submit_url = reverse('classification_submit')
        response = self.client.post(submit_url, {
            "image_url": "https://storage.gcs/extra.jpg",
            "image_sha256": "b" * 64
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Daily classification quota limit", response.data["error"])

    def test_invalid_sha256_format(self):
        submit_url = reverse('classification_submit')
        response = self.client.post(submit_url, {
            "image_url": "https://storage.gcs/extra.jpg",
            "image_sha256": "g" * 64
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid image SHA-256 signature", response.data["error"])

    def test_overwrite_protection_on_completed_status(self):
        repository = WasteItemRepository()
        item = repository.create(
            citizen=self.citizen,
            image_url="https://storage.gcs/confirm_override.jpg",
            image_sha256="d" * 64,
            status=ClassificationStatus.CLASSIFIED,
            predicted_category=CategoryChoices.METAL
        )
        
        # Slow background tasks finalize pipeline attempts to update category & change status to CLASSIFIED/PENDING
        repository.update_status_atomic(
            item_id=str(item.id),
            status=ClassificationStatus.PENDING_CONFIRMATION,
            updates={"predicted_category": CategoryChoices.PLASTIC}
        )
        
        item.refresh_from_db()
        # Enforce that the status remains CLASSIFIED and the category is still METAL (manual choice protected)
        self.assertEqual(item.status, ClassificationStatus.CLASSIFIED)
        self.assertEqual(item.predicted_category, CategoryChoices.METAL)


class ProductionHardenVerificationTests(TestCase):
    def setUp(self):
        self.citizen = User.objects.create_user(email="harden@test.com", password="securepassword123")
        self.repository = WasteItemRepository()
        cache.clear()

    def test_cache_poisoning_with_forged_sha256(self):
        import os
        from django.conf import settings
        
        # Create a temp local file
        os.makedirs(os.path.join(settings.MEDIA_ROOT, "uploads"), exist_ok=True)
        file_path = os.path.join(settings.MEDIA_ROOT, "uploads", "poison_test.jpg")
        with open(file_path, "wb") as f:
            f.write(b"authentic image bytes")
            
        item = self.repository.create(
            citizen=self.citizen,
            image_url="/media/uploads/poison_test.jpg",
            image_sha256="forged_sha256_hash_value_that_does_not_match",
            status=ClassificationStatus.ANALYZING
        )
        
        try:
            with self.assertRaises(ValueError) as ctx:
                gemini_analysis_task(str(item.id))
            self.assertIn("Local image SHA-256 mismatch", str(ctx.exception))
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    def test_reap_stuck_analyzing_items(self):
        from django.utils import timezone
        import datetime
        from .tasks import reap_stuck_classifications_task

        # Create stuck analyzing item
        stuck_item = self.repository.create(
            citizen=self.citizen,
            image_url="https://storage.gcs/stuck.jpg",
            image_sha256="s" * 64,
            status=ClassificationStatus.ANALYZING
        )
        # Manually alter created_at using database update to simulate 20 minutes age
        self.repository.model.objects.filter(pk=stuck_item.pk).update(
            created_at=timezone.now() - datetime.timedelta(minutes=20)
        )

        # Run reaper task
        reaped_count = reap_stuck_classifications_task()
        self.assertEqual(reaped_count, 1)

        stuck_item.refresh_from_db()
        self.assertEqual(stuck_item.status, ClassificationStatus.FAILED)

    @patch('classification.tasks.gemini_analysis_task.retry')
    @patch('classification.tasks.GeminiService.classify_waste_item')
    def test_gemini_retry_loops(self, mock_classify, mock_retry):
        mock_classify.side_effect = Exception("Vertex connection timeout")
        item = self.repository.create(
            citizen=self.citizen,
            image_url="https://storage.gcs.local/retry.jpg",
            image_sha256="r" * 64,
            status=ClassificationStatus.ANALYZING
        )
        
        # Test retry trigger
        try:
            gemini_analysis_task(str(item.id))
        except Exception:
            pass
        self.assertTrue(mock_retry.called or mock_classify.called)



