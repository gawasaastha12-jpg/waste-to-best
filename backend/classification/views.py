# backend/classification/views.py
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from drf_spectacular.utils import extend_schema
from core.permissions import IsOwner
from .serializers import (
    SignedURLRequestSerializer,
    SignedURLResponseSerializer,
    ClassificationSubmitSerializer,
    WasteItemSerializer,
    ClassificationConfirmSerializer
)
from .services import ImageUploadService, ClassificationPipelineService
from .repositories import WasteItemRepository

class SignedURLView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=SignedURLRequestSerializer,
        responses={200: SignedURLResponseSerializer},
        description="Generates a signed upload URL to place image files directly to the safe GCS bucket."
    )
    def post(self, request: Request) -> Response:
        serializer = SignedURLRequestSerializer(data=request.data)
        if serializer.is_valid():
            service = ImageUploadService()
            response_data = service.request_signed_upload(
                file_name=serializer.validated_data['file_name'],
                file_size=serializer.validated_data['file_size'],
                content_type=serializer.validated_data['content_type']
            )
            return Response(response_data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ClassificationSubmitView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=ClassificationSubmitSerializer,
        responses={201: WasteItemSerializer},
        description="Submits the uploaded image GCS path and signature hash to trigger async classification."
    )
    def post(self, request: Request) -> Response:
        serializer = ClassificationSubmitSerializer(data=request.data)
        if serializer.is_valid():
            service = ClassificationPipelineService()
            try:
                waste_item = service.submit_classification(
                    citizen=request.user,
                    image_url=serializer.validated_data['image_url'],
                    sha256=serializer.validated_data['image_sha256']
                )
                return Response(WasteItemSerializer(waste_item).data, status=status.HTTP_201_CREATED)
            except PermissionError as e:
                return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
            except ValueError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ClassificationStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    @extend_schema(
        responses={200: WasteItemSerializer},
        description="Polls the detailed analysis parameters and status configuration of a submitted WasteItem."
    )
    def get(self, request: Request, uuid: str) -> Response:
        repo = WasteItemRepository()
        waste_item = repo.get_by_id(uuid)
        if not waste_item:
            return Response({"error": "WasteItem not found."}, status=status.HTTP_404_NOT_FOUND)
        
        # Verify ownership using object-level authorization
        self.check_object_permissions(request, waste_item)
        
        return Response(WasteItemSerializer(waste_item).data, status=status.HTTP_200_OK)


class ClassificationConfirmView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=ClassificationConfirmSerializer,
        responses={200: WasteItemSerializer},
        description="Confirms or corrects the class category assignment of a classification item."
    )
    def post(self, request: Request) -> Response:
        serializer = ClassificationConfirmSerializer(data=request.data)
        if serializer.is_valid():
            service = ClassificationPipelineService()
            try:
                waste_item = service.confirm_classification(
                    user=request.user,
                    item_id=str(serializer.validated_data['waste_item_id']),
                    confirmed_category=serializer.validated_data['confirmed_category']
                )
                return Response(WasteItemSerializer(waste_item).data, status=status.HTTP_200_OK)
            except PermissionError:
                return Response({"error": "Unauthorized action."}, status=status.HTTP_403_FORBIDDEN)
            except ValueError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
