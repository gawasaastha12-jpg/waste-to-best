# backend/users/services.py
from django.db import transaction
from django.utils import timezone
from typing import Dict, Any, Optional
from .models import User, Profile, UserConsentLog, VerificationDocument
from .repositories import UserRepository, ProfileRepository, UserConsentLogRepository, VerificationDocumentRepository

class UserRegistrationService:
    def __init__(self) -> None:
        self.user_repo = UserRepository()
        self.profile_repo = ProfileRepository()
        self.consent_repo = UserConsentLogRepository()

    def register_user(self, registration_data: Dict[str, Any], ip_address: str) -> User:
        """
        Coordinates the transactional creation of the User account, profile, and consent logging.
        """
        email = registration_data['email']
        password = registration_data['password']
        role = registration_data['role']
        profile_data = registration_data['profile']

        with transaction.atomic():
            # 1. Create the base User
            user = self.user_repo.create(
                email=email,
                role=role
            )
            user.set_password(password)
            user.save()

            # 2. Create the associated profile metadata
            self.profile_repo.create(
                user=user,
                display_name=profile_data['display_name'],
                phone_number=profile_data.get('phone_number'),
                address_line=profile_data.get('address_line'),
                latitude=profile_data.get('latitude'),
                longitude=profile_data.get('longitude'),
                business_reg_no=profile_data.get('business_reg_no')
            )

            # 3. Log GDPR/DPDP consent explicitly
            self.consent_repo.create(
                user=user,
                consent_type="privacy_policy_v1.0",
                ip_address=ip_address
            )

        # Trigger welcome email asynchronously after transaction commits successfully
        from .tasks import send_welcome_email
        def queue_email():
            try:
                send_welcome_email.delay(str(user.id))
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to queue welcome email: {e}")

        transaction.on_commit(queue_email)

        return user

class DocumentVerificationService:
    def __init__(self) -> None:
        self.doc_repo = VerificationDocumentRepository()
        self.profile_repo = ProfileRepository()

    def submit_document(self, user: User, doc_type: str, document_url: str) -> VerificationDocument:
        """
        Registers a document for manual admin verification.
        """
        return self.doc_repo.create(
            user=user,
            doc_type=doc_type,
            document_url=document_url,
            status=VerificationDocument.StatusChoices.PENDING
        )

    def resolve_verification(
        self, doc_id: str, reviewer: User, status: str, rejection_reason: Optional[str] = None
    ) -> VerificationDocument:
        """
        Admin/Officer resolves a verification document, updating user profile verified status.
        """
        doc = self.doc_repo.get_by_id(doc_id)
        if not doc:
            raise ValueError("Verification document not found.")

        if status not in [VerificationDocument.StatusChoices.APPROVED, VerificationDocument.StatusChoices.REJECTED]:
            raise ValueError("Invalid verification resolution status.")

        with transaction.atomic():
            doc.status = status
            doc.rejection_reason = rejection_reason if status == VerificationDocument.StatusChoices.REJECTED else None
            doc.reviewed_by = reviewer
            doc.reviewed_at = timezone.now()
            doc.save()

            # If document approved, mark user profile as verified
            if status == VerificationDocument.StatusChoices.APPROVED:
                profile = self.profile_repo.get_by_user_id(doc.user.id)
                if profile:
                    profile.is_verified = True
                    profile.save()

        return doc
