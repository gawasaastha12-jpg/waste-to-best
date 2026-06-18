# backend/safety/views.py
from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from django.core.exceptions import ValidationError

from core.permissions import IsOwner, IsCitizen, IsNGO
from classification.models import WasteItem
from classification.repositories import WasteItemRepository
from classification.constants import ClassificationStatus

from .models import SafetyAssessment, ManualSafetyReview
from .constants import SafetyStatus, DecisionSource, ReviewStatus
from .repositories import SafetyRepository
from .serializers import (
    SafetyAssessmentSerializer,
    ManualSafetyReviewSerializer,
    ResolveReviewSerializer
)

class IsSafetyOwner(permissions.BasePermission):
    """
    Object-level permission for SafetyAssessment: traverses waste_item.citizen
    since SafetyAssessment has no direct user/owner field.
    """
    def has_object_permission(self, request, view, obj) -> bool:  # type: ignore
        if hasattr(obj, 'waste_item') and hasattr(obj.waste_item, 'citizen'):
            return obj.waste_item.citizen == request.user
        return False


class SafetyAssessmentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SafetyAssessment.objects.all()
    serializer_class = SafetyAssessmentSerializer
    permission_classes = [permissions.IsAuthenticated, IsSafetyOwner]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return self.queryset
        # IsOwner check: filter by citizen of the linked WasteItem
        return self.queryset.filter(waste_item__citizen=user)

    @action(detail=False, methods=["get"], url_path="history")
    def history(self, request):
        """
        GET /api/v1/safety/history/ - Retrieves safety evaluation history for the citizen.
        """
        queryset = self.get_queryset().order_by("-created_at")
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class ManualSafetyReviewViewSet(viewsets.ModelViewSet):
    queryset = ManualSafetyReview.objects.all()
    serializer_class = ManualSafetyReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return self.queryset
        # Non-staff can only see reviews assigned to them
        return self.queryset.filter(assigned_to=user)

    @action(detail=True, methods=["post"], url_path="claim")
    def claim(self, request, pk=None):
        """
        POST /api/v1/safety/reviews/<uuid>/claim/ - Claims a review atomically.
        """
        if pk is None:
            return Response({"error": "PK is required"}, status=status.HTTP_400_BAD_REQUEST)
        repo = SafetyRepository()
        try:
            review = repo.claim_review(str(pk), request.user)
            serializer = self.get_serializer(review)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve(self, request, pk=None):
        """
        POST /api/v1/safety/reviews/<uuid>/resolve/ - Resolves a manual review and commits.
        """
        if pk is None:
            return Response({"error": "PK is required"}, status=status.HTTP_400_BAD_REQUEST)
        serializer = ResolveReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        review = self.get_object()
        if review.status != ReviewStatus.IN_PROGRESS or review.assigned_to != request.user:
            return Response(
                {"error": "You must claim the review first and it must be in IN_PROGRESS status."},
                status=status.HTTP_400_BAD_REQUEST
            )

        decision = serializer.validated_data["decision"]
        notes = serializer.validated_data["review_notes"]

        repo = SafetyRepository()
        try:
            # Resolve review
            resolved_review = repo.resolve_review(str(pk), notes, decision)
            
            # Transition safety assessment
            next_status = str(SafetyStatus.APPROVED) if decision == "APPROVED" else str(SafetyStatus.BLOCKED)
            updates = {
                "decision_source": DecisionSource.MANUAL_REVIEW,
                "review_required": False,
                "review_reason": f"Manually resolved by {request.user.email} with notes: {notes}"
            }
            repo.transition_status(review.assessment.id, next_status, updates)

            # Update corresponding WasteItem status
            waste_status = str(ClassificationStatus.CLASSIFIED) if decision == "APPROVED" else str(ClassificationStatus.FAILED)
            waste_updates = {
                "disposal_instructions": f"[MANUAL SAFETY RESOLUTION] {notes}"
            }
            WasteItemRepository().update_status_atomic(review.waste_item.id, waste_status, waste_updates)

            return Response(self.get_serializer(resolved_review).data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
