# backend/users/admin.py
from django.contrib import admin
from django.contrib.auth import get_user_model
from .models import Profile, UserConsentLog, VerificationDocument

User = get_user_model()

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'role', 'eco_score_cache', 'reputation_score', 'is_active', 'is_staff', 'created_at')
    list_filter = ('role', 'is_active', 'is_staff')
    search_fields = ('email',)
    ordering = ('-created_at',)

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'user', 'phone_number', 'is_verified')
    list_filter = ('is_verified',)
    search_fields = ('display_name', 'user__email')

@admin.register(UserConsentLog)
class UserConsentLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'consent_type', 'ip_address', 'timestamp')
    list_filter = ('consent_type',)
    search_fields = ('user__email',)
    readonly_fields = ('user', 'consent_type', 'ip_address', 'timestamp')

@admin.register(VerificationDocument)
class VerificationDocumentAdmin(admin.ModelAdmin):
    list_display = ('user', 'doc_type', 'status', 'reviewed_by', 'created_at')
    list_filter = ('status', 'doc_type')
    search_fields = ('user__email',)
    readonly_fields = ('created_at',)
