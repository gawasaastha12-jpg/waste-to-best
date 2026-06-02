# backend/users/tasks.py
from celery import shared_task
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def send_welcome_email(self, user_id: str) -> None:
    """
    Sends a welcome email to newly registered users asynchronously.
    """
    try:
        user = User.objects.get(id=user_id)
        send_mail(
            subject="Welcome to WasteTrack+!",
            message=f"Hi {user.email},\n\nThank you for joining our circular economy platform!",
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@wastetrackplus.com'),
            recipient_list=[user.email],
            fail_silently=False,
        )
    except User.DoesNotExist:
        pass
