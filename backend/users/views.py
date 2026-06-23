# backend/users/views.py
from django.http import Http404
from rest_framework import viewsets, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema
from core.permissions import IsAdmin, IsMunicipalOfficer, IsOwner
from core.throttles import AuthRegisterThrottle, DocumentUploadThrottle
from .serializers import UserSerializer, UserRegisterSerializer, ProfileSerializer, VerificationDocumentSerializer
from .services import UserRegistrationService, DocumentVerificationService
from .repositories import UserRepository, ProfileRepository, VerificationDocumentRepository

class UserRegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthRegisterThrottle]

    def _get_client_ip(self, request: Request) -> str:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')

        if not ip:
            return '0.0.0.0'

        # Handle IPv4 with port (e.g. "12.34.56.78:55432")
        if '.' in ip and ':' in ip:
            ip = ip.split(':')[0].strip()

        # Handle IPv6 with brackets and port (e.g. "[2001:db8::1]:12345")
        if ip.startswith('[') and ']' in ip:
            ip = ip.split(']')[0].replace('[', '').strip()

        return ip

    @extend_schema(
        request=UserRegisterSerializer,
        responses={201: UserSerializer},
        description="Registers a new user, creates their profile, and logs data processing consent."
    )
    def post(self, request: Request) -> Response:
        serializer = UserRegisterSerializer(data=request.data)
        if serializer.is_valid():
            reg_service = UserRegistrationService()
            ip_addr = self._get_client_ip(request)
            
            # Extract deserialized values (delegating creation logic to Service layer)
            reg_data = serializer.validated_data
            user = reg_service.register_user(reg_data, ip_addr)
            
            # Generate JWT access and refresh tokens
            refresh = RefreshToken.for_user(user)
            user_data = UserSerializer(user).data
            user_data['tokens'] = {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
            return Response(user_data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ProfileViewSet(viewsets.ModelViewSet):
    serializer_class = ProfileSerializer
    # IsOwner removed: get_queryset already enforces user-scoping, and
    # get_object bypasses DRF's check_object_permissions making IsOwner a no-op.
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Users can only view or edit their own profile
        return ProfileRepository().filter_by(user_id=self.request.user.id)

    def get_object(self):
        profile = ProfileRepository().get_by_user_id(self.request.user.id)
        if profile is None:
            raise Http404("Profile not found. Please complete registration.")
        return profile

    @extend_schema(
        request=ProfileSerializer,
        responses={200: ProfileSerializer},
        description="Retrieves or updates profile metadata for the authenticated user."
    )
    def update(self, request: Request, *args, **kwargs) -> Response:
        return super().update(request, *args, **kwargs)

class VerificationDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = VerificationDocumentSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    throttle_classes = [DocumentUploadThrottle]

    def get_queryset(self):
        # Users can view their own uploaded verification documents
        return VerificationDocumentRepository().get_user_verifications(self.request.user.id)

    @extend_schema(
        request=VerificationDocumentSerializer,
        responses={201: VerificationDocumentSerializer},
        description="Uploads a verification document for review."
    )
    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            service = DocumentVerificationService()
            doc = service.submit_document(
                user=request.user,
                doc_type=serializer.validated_data['doc_type'],
                document_url=serializer.validated_data['document_url']
            )
            return Response(self.get_serializer(doc).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AdminVerificationResolveView(APIView):
    permission_classes = [IsAdmin | IsMunicipalOfficer]

    @extend_schema(
        request=VerificationDocumentSerializer,
        responses={200: VerificationDocumentSerializer},
        description="Approves or rejects an NGO/Recycler verification document."
    )
    def post(self, request: Request, doc_id: str) -> Response:
        res_status = request.data.get('status')
        reason = request.data.get('rejection_reason', '')
        
        if not res_status:
            return Response({"error": "Status is required."}, status=status.HTTP_400_BAD_REQUEST)

        service = DocumentVerificationService()
        try:
            doc = service.resolve_verification(
                doc_id=doc_id,
                reviewer=request.user,
                status=res_status,
                rejection_reason=reason
            )
            return Response(VerificationDocumentSerializer(doc).data, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
