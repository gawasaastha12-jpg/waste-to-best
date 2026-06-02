# backend/classification/permissions.py
from core.permissions import IsOwner

# Re-expose IsOwner for the classification module endpoints
__all__ = ['IsOwner']
