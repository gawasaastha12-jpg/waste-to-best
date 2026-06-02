# backend/core/permissions.py
from rest_framework import permissions
from rest_framework.request import Request
from django.views import View

class RolePermission(permissions.BasePermission):
    """
    Base permission class to check user roles.
    Subclasses must define the `required_roles` class attribute.
    """
    required_roles = []

    def has_permission(self, request: Request, view: View) -> bool:
        return (
            request.user 
            and request.user.is_authenticated 
            and hasattr(request.user, 'role')
            and request.user.role in self.required_roles
        )

class IsCitizen(RolePermission):
    required_roles = ['citizen']

class IsNGO(RolePermission):
    required_roles = ['ngo']

class IsRecycler(RolePermission):
    required_roles = ['recycler']

class IsMunicipalOfficer(RolePermission):
    required_roles = ['municipal_officer']

class IsAdmin(RolePermission):
    required_roles = ['admin']

class IsOwner(permissions.BasePermission):
    """
    Object-level permission to restrict access to resource owners.
    Checks user, owner, citizen, seller, buyer, and recipient relations dynamically.
    """
    OWNER_FIELDS = [
        "user",
        "owner",
        "citizen",
        "seller",
        "buyer",
        "recipient",
    ]

    def has_object_permission(self, request: Request, view: View, obj) -> bool:
        for field in self.OWNER_FIELDS:
            if hasattr(obj, field):
                val = getattr(obj, field)
                if val == request.user:
                    return True
        return False

