# backend/classification/exceptions.py
from rest_framework.exceptions import APIException
from rest_framework import status

class GCPServiceError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Failed to communicate with Google Cloud services."
    default_code = "gcp_service_error"

class ClassificationFailedError(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "AI classification execution failed."
    default_code = "classification_failed"
