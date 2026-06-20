# backend/classification/urls.py
from django.urls import path
from .views import (
    SignedURLView,
    ClassificationSubmitView,
    ClassificationStatusView,
    ClassificationConfirmView,
    ClassificationListView,
    LocalImageUploadView
)

urlpatterns = [
    path('', ClassificationListView.as_view(), name='classification_list'),
    path('signed-url/', SignedURLView.as_view(), name='classification_signed_url'),
    path('submit/', ClassificationSubmitView.as_view(), name='classification_submit'),
    path('status/<uuid:uuid>/', ClassificationStatusView.as_view(), name='classification_status'),
    path('confirm/', ClassificationConfirmView.as_view(), name='classification_confirm'),
    path('upload-local/<str:file_name>', LocalImageUploadView.as_view(), name='local_image_upload'),
]

