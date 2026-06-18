# backend/users/models.py
import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.conf import settings

class RoleChoices(models.TextChoices):
    CITIZEN = 'citizen', 'Citizen'
    NGO = 'ngo', 'NGO'
    RECYCLER = 'recycler', 'Recycler'
    MUNICIPAL_OFFICER = 'municipal_officer', 'Municipal Officer'
    ADMIN = 'admin', 'Admin'

class UserManager(BaseUserManager):
    def create_user(self, email: str, password: str = None, role: str = RoleChoices.CITIZEN, **extra_fields) -> 'User':
        if not email:
            raise ValueError("Users must register with an email address.")
        email = self.normalize_email(email)
        user = self.model(email=email, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str = None, **extra_fields) -> 'User':
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, role=RoleChoices.ADMIN, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    role = models.CharField(max_length=30, choices=RoleChoices.choices, default=RoleChoices.CITIZEN)
    eco_score_cache = models.IntegerField(default=0)  # Cached score from EcoPointTransactions
    reputation_score = models.DecimalField(max_digits=4, decimal_places=2, default=5.00)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self) -> str:
        return self.email

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    display_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    address_line = models.CharField(max_length=255, blank=True, null=True)
    # Using decimal floats for coordinate fallback in base setups (PostGIS Point used in full deployment)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    business_reg_no = models.CharField(max_length=100, blank=True, null=True)
    is_verified = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"{self.display_name} ({self.user.role})"

class UserConsentLog(models.Model):
    """
    Tracks GDPR & DPDP India consent logging for user data processing.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='consents')
    consent_type = models.CharField(max_length=100)  # E.g., 'privacy_policy_v1.0'
    ip_address = models.GenericIPAddressField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.user.email} - {self.consent_type}"

class VerificationDocument(models.Model):
    """
    Encapsulates business document uploads required for Recycler & NGO verification.
    """
    class DocTypeChoices(models.TextChoices):
        BUSINESS_LICENSE = 'business_license', 'Business License'
        TAX_EXEMPTION_CERT = 'tax_exemption_cert', 'Tax Exemption Cert'
        RECYCLING_PERMIT = 'recycling_permit', 'Recycling Permit'

    class StatusChoices(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='verification_documents')
    doc_type = models.CharField(max_length=50, choices=DocTypeChoices.choices)
    document_url = models.URLField(max_length=512)  # Storage path inside protected storage bucket
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.PENDING)
    rejection_reason = models.TextField(blank=True, null=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_documents')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.user.email} - {self.doc_type} ({self.status})"
