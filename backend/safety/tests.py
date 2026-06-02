# backend/safety/tests.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.utils import timezone
from unittest.mock import patch, MagicMock
import uuid

from classification.models import WasteItem
from classification.constants import ClassificationStatus, CategoryChoices
from classification.repositories import WasteItemRepository

from .models import SafetyAssessment, SafetyAuditLog, ManualSafetyReview
from .constants import SafetyStatus, RiskLevel, DecisionSource, ReviewPriority, ReviewStatus
from .repositories import SafetyRepository, SafetyStateMachine
from .services import VersionedRuleEngine, validate_safety_output, AuditGCSService
from .tasks import safety_analysis_task, reap_stuck_safety_tasks, escalate_overdue_reviews_task

User = get_user_model()

class SafetyEngineTests(TestCase):
    def setUp(self):
        self.citizen = User.objects.create_user(email="citizen@safety.com", password="securepassword123")
        self.reviewer_a = User.objects.create_user(email="reviewer_a@safety.com", password="securepassword123", is_staff=True)
        self.reviewer_b = User.objects.create_user(email="reviewer_b@safety.com", password="securepassword123", is_staff=True)
        
        self.waste_repo = WasteItemRepository()
        self.safety_repo = SafetyRepository()
        
        self.waste_item = self.waste_repo.create(
            citizen=self.citizen,
            image_url="https://storage.gcs/waste.jpg",
            image_sha256="c" * 64,
            status=ClassificationStatus.ANALYZING
        )
        cache.clear()

    def test_rule_override_dominance(self):
        """
        Verify that deterministic rules override AI safety output.
        """
        # If item category is Hazardous (like Lithium Battery) and Gemini attempts to say SAFE,
        # rule engine overrides to CRITICAL risk level and DecisionSource.RULE_OVERRIDE.
        res = VersionedRuleEngine.evaluate(CategoryChoices.HAZARDOUS, ["lithium battery"])
        self.assertIsNotNone(res)
        self.assertEqual(res["risk_level"], RiskLevel.CRITICAL)
        self.assertEqual(res["decision_source"], DecisionSource.RULE_ENGINE)  # or RULE_OVERRIDE depending on logic
        self.assertTrue(res["review_required"])

    def test_safety_audit_log_immutability(self):
        """
        Verifies that SafetyAuditLog records cannot be modified or deleted.
        """
        log = SafetyAuditLog.objects.create(
            waste_item=self.waste_item,
            payload_uri="gs://wastetrack-audit/test.json.gz",
            payload_hash="h" * 64,
            decision="APPROVED",
            reason=""
        )

        with self.assertRaises(ValidationError):
            log.payload_uri = "gs://modified/uri.json.gz"
            log.save()

        with self.assertRaises(ValidationError):
            log.delete()

    def test_manual_review_claiming_race(self):
        """
        Verifies that Reviewer A and Reviewer B claiming same review concurrently succeeds for only one.
        """
        assessment = self.safety_repo.get_or_create_assessment(str(self.waste_item.id))
        review = self.safety_repo.create_manual_review(
            waste_item_id=str(self.waste_item.id),
            assessment_id=str(assessment.id),
            priority=ReviewPriority.HIGH
        )

        # Claimer A claims review
        claimed_review = self.safety_repo.claim_review(str(review.id), self.reviewer_a)
        self.assertEqual(claimed_review.assigned_to, self.reviewer_a)
        self.assertEqual(claimed_review.status, ReviewStatus.IN_PROGRESS)

        # Claimer B tries to claim but gets ValidationError
        with self.assertRaises(ValidationError):
            self.safety_repo.claim_review(str(review.id), self.reviewer_b)

    def test_gemini_out_of_bounds_validation(self):
        """
        Verifies that safety validations raise ValidationError for out of bounds values.
        """
        malformed_output = {
            "risk_level": "SAFE",
            "risk_score": 1.4,  # Out of bounds
            "hazard_categories": [],
            "safe_disposal_method": "Throw in bin",
            "approved_upcycling": [],
            "blocked_upcycling": [],
            "review_required": False,
            "review_reason": ""
        }
        with self.assertRaises(ValidationError) as ctx:
            validate_safety_output(malformed_output)
        self.assertIn("risk_score must be between 0.0 and 1.0 inclusive.", str(ctx.exception))

    def test_reap_stuck_safety_tasks(self):
        """
        Verify that stuck safety analysis tasks are reaped to FAILED.
        """
        assessment = self.safety_repo.get_or_create_assessment(str(self.waste_item.id))
        self.safety_repo.transition_status(assessment.id, SafetyStatus.ANALYZING)
        
        # Artificially set updated_at back in time to simulate OOM crash
        SafetyAssessment.objects.filter(pk=assessment.id).update(
            updated_at=timezone.now() - timezone.timedelta(minutes=20)
        )

        reaped_count = reap_stuck_safety_tasks()
        self.assertEqual(reaped_count, 1)

        assessment.refresh_from_db()
        self.assertEqual(assessment.status, SafetyStatus.FAILED)

        # Linked WasteItem must transition to FAILED
        self.waste_item.refresh_from_db()
        self.assertEqual(self.waste_item.status, ClassificationStatus.FAILED)

    @patch('safety.tasks.SafetyAIService.analyze_safety')
    @patch('safety.tasks.AuditGCSService.upload_to_gcs')
    def test_gemini_safety_confidence_threshold(self, mock_gcs, mock_ai):
        """
        Verify that safety scores below MIN_SAFETY_CONFIDENCE trigger manual review.
        """
        mock_gcs.return_value = "gs://wastetrack-audit/mock.json.gz"
        mock_ai.return_value = {
            "risk_level": "LOW",
            "risk_score": 0.50,  # Below threshold 0.70
            "hazard_categories": [],
            "safe_disposal_method": "Rinse bottle.",
            "approved_upcycling": [],
            "blocked_upcycling": [],
            "review_required": False,
            "review_reason": ""
        }

        payload = {
            "item_id": str(self.waste_item.id),
            "labels": ["plastic bottle"],
            "gemini_result": {"category": "Plastic", "confidence": 0.90}
        }

        res_payload = safety_analysis_task(payload)
        self.assertEqual(res_payload["safety_status"], SafetyStatus.REVIEW_REQUIRED)

        assessment = self.safety_repo.get_by_waste_item_id(str(self.waste_item.id))
        self.assertTrue(assessment.review_required)
        self.assertIn("confidence", assessment.review_reason.lower())

    @patch('safety.tasks.SafetyAIService.analyze_safety')
    def test_circuit_breaker_tripping_fallback(self, mock_ai):
        """
        Tripping circuit breaker switches off Gemini Safety queries and triggers manual review queue fallback.
        """
        mock_ai.side_effect = Exception("Vertex connection failed")
        payload = {
            "item_id": str(self.waste_item.id),
            "labels": ["plastic bottle"],
            "gemini_result": {"category": "Plastic", "confidence": 0.90}
        }

        # Force failure count to trip circuit breaker
        for _ in range(12):
            try:
                safety_analysis_task(payload)
            except Exception:
                pass

        # CB should now be open, and subsequent tasks fallback deterministically
        success_item = self.waste_repo.create(
            citizen=self.citizen,
            image_url="https://storage.gcs/cb_test.jpg",
            image_sha256="d" * 64,
            status=ClassificationStatus.ANALYZING
        )
        
        cb_payload = {
            "item_id": str(success_item.id),
            "labels": ["plastic bottle"],
            "gemini_result": {"category": "Plastic", "confidence": 0.90}
        }

        # Runs deterministically and sets review_required
        res = safety_analysis_task(cb_payload)
        self.assertEqual(res["safety_status"], SafetyStatus.REVIEW_REQUIRED)
        
        assess = self.safety_repo.get_by_waste_item_id(str(success_item.id))
        self.assertIn("offline", assess.review_reason)

    def test_state_transition_constraints(self):
        """
        Enforce state transitions safety constraints (e.g. APPROVED -> ANALYZING illegal).
        """
        assessment = self.safety_repo.get_or_create_assessment(str(self.waste_item.id))
        self.safety_repo.transition_status(assessment.id, SafetyStatus.ANALYZING)
        self.safety_repo.transition_status(assessment.id, SafetyStatus.APPROVED)

        with self.assertRaises(ValidationError):
            self.safety_repo.transition_status(assessment.id, SafetyStatus.ANALYZING)
