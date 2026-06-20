# backend/safety/services_ai.py
import os
import json
import logging
from PIL import Image
from django.conf import settings
import google.generativeai as genai
from typing import Dict, Any, List
from .constants import RiskLevel, HazardCategory
from classification.exceptions import GCPServiceError

logger = logging.getLogger("safety.ai")

class SafetyAIService:
    def __init__(self) -> None:
        self.model_name = "gemini-1.5-flash"
        self.initialized = False
        api_key = getattr(settings, "GEMINI_API_KEY", "")
        if api_key:
            try:
                genai.configure(api_key=api_key)
                self.initialized = True
            except Exception as e:
                logger.warning(f"google-generativeai configuration failed in SafetyAIService: {str(e)}")
        else:
            logger.warning("GEMINI_API_KEY settings attribute is missing or empty. Mock safety engine active.")

    def analyze_safety(self, image_url: str, category: str, labels: List[str]) -> Dict[str, Any]:
        """
        Uses Google Gemini 1.5 Flash to assess safety and hazard levels of a classified waste item.
        """
        # Define choices to instruct the AI
        allowed_risk_levels = [r.value for r in RiskLevel]
        allowed_hazard_categories = [h.value for h in HazardCategory]

        prompt = f"""
        You are an expert AI Safety Engine verifying a waste item with predicted category: '{category}'.
        Analyze the image for safety hazards (toxic chemicals, fire risk, batteries, medical/sharps, etc.).
        
        Output EXACTLY a JSON structure matching this schema:
        {{
          "risk_level": "SAFE | LOW | MEDIUM | HIGH | CRITICAL",
          "risk_score": Float (between 0.0 and 1.0),
          "hazard_categories": [list containing matching categories from: {', '.join(allowed_hazard_categories)}],
          "safe_disposal_method": "String detailing safe disposal rules",
          "approved_upcycling": ["List of approved safe upcycling ideas"],
          "blocked_upcycling": ["List of prohibited hazardous upcycling/DIY ideas"],
          "review_required": Boolean (true if any danger or ambiguity is detected),
          "review_reason": "Explanation of why manual review is needed or blank if not required"
        }}
        """

        if not self.initialized:
            # Fallback simulated response
            return {
                "risk_level": RiskLevel.SAFE.value,
                "risk_score": 0.10,
                "hazard_categories": [],
                "safe_disposal_method": "Wash container and place in standard plastic recycling stream.",
                "approved_upcycling": ["Plastic planters", "Storage bins"],
                "blocked_upcycling": ["Do not burn or melt plastic containers indoors."],
                "review_required": False,
                "review_reason": ""
            }

        try:
            # Resolve local image path
            relative_path = image_url.lstrip("/")
            if relative_path.startswith("media/"):
                relative_path = relative_path[6:]
            local_image_path = os.path.join(settings.MEDIA_ROOT, relative_path)

            if not os.path.exists(local_image_path):
                # Fallback path resolution
                local_image_path = os.path.join(settings.MEDIA_ROOT, "uploads", os.path.basename(image_url))

            if not os.path.exists(local_image_path):
                raise FileNotFoundError(f"Local image file not found at: {local_image_path}")

            # Open image using Pillow
            img = Image.open(local_image_path)

            # Define model
            model = genai.GenerativeModel(self.model_name)
            
            # Request content generation in JSON mode
            response = model.generate_content(
                [img, prompt],
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.0
                }
            )
            result_data = json.loads(response.text)
            return result_data
        except Exception as e:
            logger.exception("Gemini safety analysis processing failure.")
            raise GCPServiceError(f"Gemini Safety analysis failed: {str(e)}")
