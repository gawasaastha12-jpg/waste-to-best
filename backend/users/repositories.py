# backend/users/repositories.py
from typing import Optional, List, Any
from decimal import Decimal
from core.repositories import BaseRepository
from .models import User, Profile, UserConsentLog, VerificationDocument

class UserRepository(BaseRepository[User]):
    model = User

    def get_by_email(self, email: str) -> Optional[User]:
        return self.model.objects.filter(email=email).first()

    def update_reputation(self, user: User, delta: float) -> User:
        from django.db import transaction
        with transaction.atomic():
            locked_user = self.model.objects.select_for_update().get(pk=user.pk)
            locked_user.reputation_score = Decimal(str(max(0.00, min(5.00, float(locked_user.reputation_score) + delta))))
            locked_user.save()
        return locked_user

class ProfileRepository(BaseRepository[Profile]):
    model = Profile

    def get_by_user_id(self, user_id: Any) -> Optional[Profile]:
        return self.model.objects.filter(user_id=user_id).first()

class UserConsentLogRepository(BaseRepository[UserConsentLog]):
    model = UserConsentLog

    def get_user_consent_history(self, user_id: Any) -> List[UserConsentLog]:
        return list(self.filter_by(user_id=user_id))

class VerificationDocumentRepository(BaseRepository[VerificationDocument]):
    model = VerificationDocument

    def get_pending_verifications(self) -> List[VerificationDocument]:
        return list(self.filter_by(status=VerificationDocument.StatusChoices.PENDING))

    def get_user_verifications(self, user_id: Any) -> List[VerificationDocument]:
        return list(self.filter_by(user_id=user_id))
