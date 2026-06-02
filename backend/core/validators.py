# backend/core/validators.py
import os
import magic
from django.core.exceptions import ValidationError

ALLOWED_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png']
ALLOWED_MIME_TYPES = ['application/pdf', 'image/jpeg', 'image/png']
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

def validate_file_security(file_obj) -> None:
    """
    Validates file upload size, extension signature, and byte-level MIME type.
    """
    # 1. Size Validation
    if file_obj.size > MAX_FILE_SIZE:
        raise ValidationError(f"File size exceeds the limit of {MAX_FILE_SIZE / (1024 * 1024)} MB.")

    # 2. Extension Validation
    ext = os.path.splitext(file_obj.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"Unsupported file extension: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

    # 3. MIME Signature Validation
    # Read the first 2048 bytes to detect the file signature
    header = file_obj.read(2048)
    file_obj.seek(0)
    
    try:
        mime_type = magic.from_buffer(header, mime=True)
    except Exception as e:
        raise ValidationError("Could not verify file signature.")

    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValidationError(f"Unsupported media type: {mime_type}. Allowed: PDF, JPEG, PNG.")
