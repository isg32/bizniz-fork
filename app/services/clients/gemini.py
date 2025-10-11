# app/services/clients/gemini.py

import google.generativeai as genai
from typing import List, Union, Dict
import base64
from app.core.config import settings

class GeminiClient:
    """
    A unified client for interacting with Google Gemini models.
    This client is designed to be initialized once and reused.
    """
    def __init__(self):
        self.text_model = None
        self.image_model = None
        self._initialized = False

    def init_app(self):
        """
        Initializes the API configuration and models. This should be called
        once at application startup.
        """
        if not settings.GEMINI_API_KEY:
            print("WARNING: GEMINI_API_KEY is not set. All Gemini services will be unavailable.")
            return

        try:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            
            # Initialize the text model
            self.text_model = genai.GenerativeModel('gemini-2.5-flash')
            print("Gemini TEXT client initialized successfully.")
            
            # Initialize the image model
            self.image_model = genai.GenerativeModel('gemini-2.5-flash')
            print("Gemini IMAGE client initialized successfully.")

            self._initialized = True
        except Exception as e:
            print(f"FATAL: Could not initialize Gemini clients. Error: {e}")

    def generate_chat_response(self, prompt: str) -> str:
        """Generates a chat response from the Gemini text model."""
        if not self._initialized or not self.text_model:
            raise Exception("Gemini text model is not initialized.")
        
        try:
            response = self.text_model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"Error calling Gemini Text API: {e}")
            raise  # Re-raise the exception to be handled by the API layer

    def generate_image(self, prompt: str) -> str:
        """Generates an image and returns a Base64 encoded Data URI."""
        if not self._initialized or not self.image_model:
            raise Exception("Gemini image model is not initialized.")

        try:
            response = self.image_model.generate_content(prompt)
            image_part = next((p for p in response.candidates[0].content.parts if hasattr(p, 'inline_data')), None)

            if not image_part:
                raise Exception("Image generation failed. The model did not return any image data.")

            mime_type = image_part.inline_data.mime_type
            raw_bytes = image_part.inline_data.data
            base64_data = base64.b64encode(raw_bytes).decode('utf-8')
            return f"data:{mime_type};base64,{base64_data}"
        except Exception as e:
            print(f"Error calling Gemini Image API: {e}")
            raise # Re-raise the exception

# Create a single, shared instance of the client that the whole application will use.
# This is called a "singleton" pattern.
gemini_client = GeminiClient()