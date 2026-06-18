# backend/classification/services_gcp.py
import datetime
import os
import json
import logging
from typing import Dict, Any, List
from django.conf import settings
from google.cloud import storage, vision
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from .exceptions import GCPServiceError

logger = logging.getLogger("classification.gcp")

class GCSService:
    def __init__(self) -> None:
        self.project_id = os.environ.get("GCP_PROJECT_ID")
        self.bucket_name = os.environ.get("GCS_BUCKET_NAME", "wastetrack-images")
        
        # Initialize storage client only if credentials exist or default application credentials are set
        try:
            self.client = storage.Client(project=self.project_id)
        except Exception as e:
            logger.warning("GCS client initialization failed. Falling back to simulated storage interface.")
            self.client = None

    def generate_signed_upload_url(self, blob_name: str, expiration_minutes: int = 15, content_type: str = "image/jpeg") -> str:
        """
        Generates a signed URL to allow secure client-side uploads directly to a private GCS bucket.
        """
        if not self.client:
            # Local development fallback when credentials are not configured
            return f"https://storage.gcs.local/{self.bucket_name}/{blob_name}"

        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(blob_name)
            url = blob.generate_signed_url(
                version="v4",
                expiration=datetime.timedelta(minutes=expiration_minutes),
                method="PUT",
                content_type=content_type
            )
            return url
        except Exception as e:
            logger.exception("GCS signed URL generation failure.")
            raise GCPServiceError(f"GCS signed URL creation failed: {str(e)}")


class VisionAIService:
    def __init__(self) -> None:
        try:
            self.client = vision.ImageAnnotatorClient()
        except Exception as e:
            logger.warning("Vision AI client initialization failed. Annotator fallbacks will be active.")
            self.client = None

    def analyze_image_labels(self, image_url: str) -> List[str]:
        """
        Queries Google Cloud Vision API to extract image label annotations.
        """
        if not self.client:
            # Simulated local mock response
            return ["plastic bottle", "beverage container", "PET polymer", "waste recycling"]

        try:
            image = vision.Image()
            # Vision API allows pointing directly to a public/authenticated GCS source path
            if image_url.startswith("gs://"):
                image.source.image_uri = image_url
            else:
                image.source.image_uri = image_url

            response = self.client.label_detection(image=image)
            if response.error.message:
                raise GCPServiceError(f"Vision API service returned error: {response.error.message}")

            labels = [label.description.lower() for label in response.label_annotations]
            return labels
        except Exception as e:
            logger.exception("Vision AI label detection failure.")
            raise GCPServiceError(f"Vision AI labeling failed: {str(e)}")


class GeminiService:
    def __init__(self) -> None:
        self.project_id = os.environ.get("GCP_PROJECT_ID")
        self.location = os.environ.get("GCP_LOCATION", "us-central1")
        self.model_name = "gemini-1.5-flash-001"
        
        self.initialized = False
        try:
            vertexai.init(project=self.project_id, location=self.location)
            self.initialized = True
        except Exception as e:
            logger.warning("Vertex AI initialization failed. Mock Gemini engine active.")

    def classify_waste_item(self, image_url: str, vision_labels: List[str]) -> Dict[str, Any]:
        """
        Uses Vertex AI Gemini 1.5 Flash to categorize a waste item and suggest circular actions.
        Enforces structured JSON schema response format.
        """
        # Strict validation taxonomy
        allowed_categories = ["Plastic", "Paper", "Glass", "Metal", "Organic", "Textile", "E-Waste", "Hazardous", "Mixed Waste"]

        prompt = f"""
        Analyze the waste item image and Vision AI labels: {', '.join(vision_labels)}.
        Categorize the item into exactly one of the following categories: {', '.join(allowed_categories)}.

        Enforce this strict JSON output schema:
        {{
          "category": "String (must match taxonomy exactly)",
          "confidence": Float (between 0.0 and 1.0),
          "alternatives": ["Alternative Category 1", "Alternative Category 2"],
          "requires_clarification": Boolean (true if confidence is low, e.g. < 0.60),
          "clarification_questions": ["Question 1", "Question 2"],
          "disposal_instructions": "String detailing safe disposal rules",
          "upcycling_guides": ["Idea 1", "Idea 2"]
        }}
        """

        if not self.initialized:
            # Simulated local mock response when Vertex AI is not initialized
            return {
                "category": "Plastic",
                "confidence": 0.9400,
                "alternatives": ["Metal", "Mixed Waste"],
                "requires_clarification": False,
                "clarification_questions": [],
                "disposal_instructions": "Rinse bottle, remove plastic cap, place in green recycling bin.",
                "upcycling_guides": ["Cut bottom half to make a seed starter pot.", "Create a DIY phone stand."]
            }

        try:
            model = GenerativeModel(
                self.model_name,
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Mount media content from URI
            mime_type = "image/png" if image_url.lower().endswith(".png") else "image/jpeg"
            image_part = Part.from_uri(mime_type=mime_type, uri=image_url)
            
            response = model.generate_content([image_part, prompt])
            result_data = json.loads(response.text)

            # Validate structural compliance
            if "category" not in result_data or result_data["category"] not in allowed_categories:
                result_data["category"] = "Mixed Waste"
            
            if "confidence" not in result_data:
                result_data["confidence"] = 0.50
                
            return result_data
        except Exception as e:
            logger.exception("Gemini Vertex AI classification processing failure.")
            raise GCPServiceError(f"Gemini processing failed: {str(e)}")
