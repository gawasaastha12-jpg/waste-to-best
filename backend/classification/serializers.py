# backend/classification/serializers.py
from rest_framework import serializers
from .models import WasteItem
from .constants import CategoryChoices
from safety.serializers import SafetyAssessmentSerializer

class SignedURLRequestSerializer(serializers.Serializer):
    file_name = serializers.CharField(max_length=255)
    file_size = serializers.IntegerField(min_value=1)
    content_type = serializers.CharField(max_length=100)

    def validate_content_type(self, value):
        allowed = ['image/jpeg', 'image/png']
        if value not in allowed:
            raise serializers.ValidationError("Only JPEG and PNG file uploads are supported.")
        return value

class SignedURLResponseSerializer(serializers.Serializer):
    signed_url = serializers.URLField()
    image_url = serializers.URLField()
    file_name = serializers.CharField()

class ClassificationSubmitSerializer(serializers.Serializer):
    image_url = serializers.URLField()
    image_sha256 = serializers.CharField(max_length=64, min_length=64)

class WasteItemSerializer(serializers.ModelSerializer):
    safety_assessment = SafetyAssessmentSerializer(read_only=True)

    class Meta:
        model = WasteItem
        fields = [
            'id',
            'citizen',
            'image_url',
            'image_sha256',
            'status',
            'predicted_category',
            'confidence_score',
            'alternatives',
            'clarification_questions',
            'disposal_instructions',
            'upcycling_guides',
            'safety_assessment',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id', 'citizen', 'status', 'predicted_category', 'confidence_score',
            'alternatives', 'clarification_questions', 'disposal_instructions',
            'upcycling_guides', 'safety_assessment', 'created_at', 'updated_at'
        ]

class ClassificationConfirmSerializer(serializers.Serializer):
    waste_item_id = serializers.UUIDField()
    confirmed_category = serializers.ChoiceField(choices=CategoryChoices.choices)

