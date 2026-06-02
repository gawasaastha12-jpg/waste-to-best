# backend/safety/urls.py
from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import SafetyAssessmentViewSet, ManualSafetyReviewViewSet

router = SimpleRouter()
router.register(r'reviews', ManualSafetyReviewViewSet, basename='safety_reviews')
router.register(r'', SafetyAssessmentViewSet, basename='safety_assessments')

urlpatterns = [
    path('', include(router.urls)),
]
