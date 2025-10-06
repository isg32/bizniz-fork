
import google.generativeai as genai
from app.core.config import settings

# Configure the Gemini client at the module level
try:
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    print("Gemini client initialized successfully.")
except Exception as e:
    model = None
    print(f"WARNING: Could not initialize Gemini client. Service will be unavailable. Error: {e}")


def generate_chat_response(prompt: str) -> str | None:
    """
    Generates a chat response from the Gemini model.
    Returns the response text on success, or None on failure.
    """
    if not model:
        print("ERROR: Gemini service called but model is not initialized.")
        return None
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return None
