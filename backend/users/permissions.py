# backend/users/permissions.py
from rest_framework import permissions

class IsVerified(permissions.BasePermission):
    """
    Blocks access for NGOs or Recyclers that have not completed verification checks.
    """
    def has_permission(self, request, view):  # type: ignore[override]
        return (
            request.user 
            and request.user.is_authenticated 
            and hasattr(request.user, 'profile')
            and (request.user.role in ['citizen', 'admin', 'municipal_officer'] or request.user.profile.is_verified)
        )
