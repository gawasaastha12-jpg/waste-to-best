# backend/core/throttles.py
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle

class AuthRegisterThrottle(AnonRateThrottle):
    rate = '5/minute'

class AuthLoginThrottle(AnonRateThrottle):
    rate = '5/minute'

class DocumentUploadThrottle(UserRateThrottle):
    rate = '10/minute'
