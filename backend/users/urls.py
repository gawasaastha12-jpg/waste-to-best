# backend/users/urls.py
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import UserRegisterView, ProfileViewSet, VerificationDocumentViewSet, AdminVerificationResolveView

profile_detail = ProfileViewSet.as_view({
    'get': 'retrieve',
    'patch': 'partial_update'
})

doc_list = VerificationDocumentViewSet.as_view({
    'get': 'list',
    'post': 'create'
})

urlpatterns = [
    # Auth Token management
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Registration & profile endpoints
    path('register/', UserRegisterView.as_view(), name='user_register'),
    path('profile/', profile_detail, name='profile_detail'),
    
    # NGO/Recycler Verification documents
    path('documents/', doc_list, name='verification_documents'),
    path('verifications/<uuid:doc_id>/resolve/', AdminVerificationResolveView.as_view(), name='admin_resolve_verification'),
]
