# backend/classification/services_gcp.py
import os
import json
import logging
from PIL import Image
from typing import Dict, Any, List, Optional
from django.conf import settings
import google.generativeai as genai
from .exceptions import GCPServiceError

logger = logging.getLogger("classification.gcp")

class GeminiService:
    def __init__(self) -> None:
        self.model_name = "gemini-2.5-flash"
        self.initialized = False
        api_key = getattr(settings, "GEMINI_API_KEY", "")
        if api_key:
            try:
                genai.configure(api_key=api_key)
                self.initialized = True
            except Exception as e:
                logger.warning(f"google-generativeai configuration failed: {str(e)}")
        else:
            logger.warning("GEMINI_API_KEY settings attribute is missing or empty. Mock Gemini engine active.")

    def classify_waste_item(self, image_url: str, local_image_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Uses Google Gemini 1.5 Flash to categorize a waste item and suggest circular actions.
        Enforces structured JSON schema response format.
        """
        # Strict validation taxonomy
        allowed_categories = ["Plastic", "Paper", "Glass", "Metal", "Organic", "Textile", "E-Waste", "Hazardous", "Mixed Waste"]

        prompt = f"""
        Analyze this waste item image.
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
            # Simulated local mock response when Gemini is not initialized
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
            # Resolve local image path if not provided
            if not local_image_path:
                relative_path = image_url.lstrip("/")
                if relative_path.startswith("media/"):
                    relative_path = relative_path[6:]
                local_image_path = os.path.join(settings.MEDIA_ROOT, relative_path)

            if not os.path.exists(local_image_path):
                raise FileNotFoundError(f"Local image file not found at: {local_image_path}")

            # Open image using Pillow
            img = Image.open(local_image_path)

            # Define model
            model = genai.GenerativeModel(self.model_name)
            
            # Request content generation in JSON mode
            response = model.generate_content(
                [img, prompt],
                generation_config={"response_mime_type": "application/json"}
            )
            result_data = json.loads(response.text)

            # Validate structural compliance
            if "category" not in result_data or result_data["category"] not in allowed_categories:
                result_data["category"] = "Mixed Waste"
            
            if "confidence" not in result_data:
                result_data["confidence"] = 0.50
                
            return result_data
        except Exception as e:
            logger.exception("Gemini classification processing failure.")
            raise GCPServiceError(f"Gemini processing failed: {str(e)}")
