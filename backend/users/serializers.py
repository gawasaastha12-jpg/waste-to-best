# backend/users/serializers.py
from django.core.files.storage import default_storage
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Profile, UserConsentLog, VerificationDocument, RoleChoices
from core.validators import validate_file_security

User = get_user_model()

class ProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    role = serializers.CharField(source='user.role', read_only=True)
    eco_score = serializers.IntegerField(source='user.eco_score_cache', read_only=True)
    reputation_score = serializers.DecimalField(source='user.reputation_score', max_digits=3, decimal_places=2, read_only=True)

    class Meta:
        model = Profile
        fields = [
            'display_name',
            'phone_number',
            'address_line',
            'latitude',
            'longitude',
            'business_reg_no',
            'is_verified',
            'email',
            'role',
            'eco_score',
            'reputation_score'
        ]
        read_only_fields = ['is_verified', 'email', 'role', 'eco_score', 'reputation_score']


class UserConsentLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserConsentLog
        fields = ['consent_type', 'ip_address', 'timestamp']
        read_only_fields = ['ip_address', 'timestamp']

class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'role',
            'eco_score_cache',
            'reputation_score',
            'profile',
            'created_at'
        ]
        read_only_fields = ['id', 'eco_score_cache', 'reputation_score', 'created_at']

class UserRegisterSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer()
    password = serializers.CharField(write_only=True, min_length=8)
    consent = serializers.BooleanField(write_only=True)

    class Meta:
        model = User
        fields = ['email', 'password', 'role', 'profile', 'consent']

    def validate_role(self, value):
        if value != RoleChoices.CITIZEN:
            raise serializers.ValidationError("Role assignment is restricted.")
        return value

    def validate_consent(self, value):
        if not value:
            raise serializers.ValidationError("Consent to privacy policy is required.")
        return value

    def create(self, validated_data):
        # User creation is delegated to UserRegistrationService for transactional
        # consistency. Calling serializer.save() directly is not supported.
        raise NotImplementedError(
            "User creation must go through UserRegistrationService.register_user(). "
            "Do not call serializer.save() directly."
        )

class VerificationDocumentSerializer(serializers.ModelSerializer):
    document_file = serializers.FileField(write_only=True, validators=[validate_file_security])

    class Meta:
        model = VerificationDocument
        fields = [
            'id',
            'doc_type',
            'document_url',
            'document_file',
            'status',
            'rejection_reason',
            'created_at'
        ]
        read_only_fields = ['id', 'document_url', 'status', 'rejection_reason', 'created_at']

    def validate(self, attrs):
        file_obj = attrs.pop('document_file')
        # Save the uploaded file to storage (local filesystem in dev, GCS in production)
        saved_path = default_storage.save(
            f"verification-docs/{file_obj.name}",
            file_obj
        )
        attrs['document_url'] = default_storage.url(saved_path)
        return attrs
