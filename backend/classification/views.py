# backend/classification/views.py
import os
from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
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
        print("REQUEST DATA:", request.data)
        serializer = SignedURLRequestSerializer(data=request.data)
        if serializer.is_valid():
            service = ImageUploadService()
            response_data = service.request_signed_upload(
                file_name=serializer.validated_data['file_name'],
                file_size=serializer.validated_data['file_size'],
                content_type=serializer.validated_data['content_type'],
                request=request
            )
            return Response(response_data, status=status.HTTP_200_OK)
        print("SERIALIZER ERRORS:", serializer.errors)
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


class ClassificationListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={200: WasteItemSerializer(many=True)},
        description="Retrieves a paginated list of classification waste items for the authenticated citizen."
    )
    def get(self, request: Request) -> Response:
        repo = WasteItemRepository()
        try:
            limit = int(request.query_params.get('limit', 20))
            offset = int(request.query_params.get('offset', 0))
        except (ValueError, TypeError):
            limit = 20
            offset = 0

        data = repo.get_paginated_items(
            citizen_id=str(request.user.id),
            limit=limit,
            offset=offset
        )
        
        serializer = WasteItemSerializer(data['results'], many=True)
        return Response({
            'count': data['count'],
            'results': serializer.data
        }, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name='dispatch')
class LocalImageUploadView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(exclude=True)
    def put(self, request: Request, file_name: str) -> Response:
        """
        Receives raw image bytes from client and saves them to local storage.
        """
        try:
            upload_dir = os.path.join(settings.MEDIA_ROOT, 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            
            file_path = os.path.join(upload_dir, file_name)
            with open(file_path, 'wb') as f:
                f.write(request.body)
                
            return Response({"status": "success"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

