# backend/classification/repositories.py
from typing import Optional, List, Dict, Any
from django.db import transaction
from django.core.paginator import Paginator, Page
from core.repositories import BaseRepository
from .models import WasteItem
from .constants import ClassificationStatus

class WasteItemRepository(BaseRepository[WasteItem]):
    model = WasteItem

    def get_by_sha256(self, sha256: str) -> Optional[WasteItem]:
        """
        Look up the latest successfully classified WasteItem with the matching SHA-256 hash.
        """
        return self.model.objects.filter(
            image_sha256=sha256,
            status=ClassificationStatus.CLASSIFIED
        ).first()

    def filter_by_citizen_and_status(self, citizen_id: str, status: Optional[str] = None) -> List[WasteItem]:
        """
        Filters classification items by citizen and status.
        """
        query_params = {'citizen_id': citizen_id}
        if status:
            query_params['status'] = status
        return list(self.model.objects.filter(**query_params))

    def get_paginated_items(self, citizen_id: str, limit: int, offset: int) -> Dict[str, Any]:
        """
        Wraps manual offset pagination for classification query responses.
        """
        queryset = self.model.objects.filter(citizen_id=citizen_id)
        total = queryset.count()
        results = list(queryset[offset:offset + limit])
        return {
            'count': total,
            'results': results
        }

    def update_status_atomic(self, item_id: str, status: str, updates: Optional[Dict[str, Any]] = None) -> WasteItem:
        """
        Locks the row and updates the classification fields atomically. Protects manual citizen confirmations.
        """
        with transaction.atomic():
            item = self.model.objects.select_for_update().get(pk=item_id)
            
            # If the user has already manually confirmed classification, ignore slow async tasks updates
            if item.status == ClassificationStatus.CLASSIFIED and status != ClassificationStatus.CLASSIFIED:
                return item
            
            item.status = status
            if updates:
                for key, val in updates.items():
                    if hasattr(item, key):
                        setattr(item, key, val)
            item.save()
        return item
