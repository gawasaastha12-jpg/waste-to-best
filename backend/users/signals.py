# backend/users/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.cache import cache
from .models import Profile

@receiver(post_save, sender=Profile)
def clear_profile_cache(sender, instance, **kwargs) -> None:
    """
    Invalidates profile caches when a user profile is updated.
    """
    cache_key = f"profile:cache:{instance.user.id}"
    cache.delete(cache_key)
