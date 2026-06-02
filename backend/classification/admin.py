# backend/classification/admin.py
from django.contrib import admin
from .models import WasteItem

@admin.register(WasteItem)
class WasteItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'citizen', 'predicted_category', 'confidence_score', 'status', 'created_at')
    list_filter = ('status', 'predicted_category', 'created_at')
    search_fields = ('id', 'citizen__email', 'image_sha256')
    readonly_fields = ('id', 'created_at', 'updated_at')
