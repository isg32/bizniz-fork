# app/api/v1/services/gemini.py

from fastapi import APIRouter, Depends, Body, Form, HTTPException, status

from app.core.dependencies import get_current_api_user
from app.schemas.user import User as UserSchema
from app.services.clients.gemini import gemini_client
from app.core.decorators import require_coins

router = APIRouter()

# --- Gemini Language Model Endpoint ---

GEMINI_TEXT_COST = 1.0

@router.post("/text/chat", summary="Chat with Gemini LLM")
# MODIFICATION: Add a descriptive string for the transaction log.
@require_coins(cost=GEMINI_TEXT_COST, description="Gemini Text Generation")
async def chat_with_gemini(
    prompt: str = Body(
        ...,
        embed=True,
        min_length=1,
        max_length=4000,
        description="The text prompt to send to the language model."
    ),
    current_user: UserSchema = Depends(get_current_api_user),
):
    """
    Handles chat requests to the Gemini LLM service.
    """
    try:
        ai_response = gemini_client.generate_chat_response(prompt=prompt)
        return {"response": ai_response}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"The Language Model service failed: {e}"
        )


# --- Gemini Image Generation Endpoint ---

IMAGE_GENERATION_COST = 5.0

@router.post("/image/generate", summary="Generate Image with Gemini")
# MODIFICATION: Add a descriptive string for the transaction log.
@require_coins(cost=IMAGE_GENERATION_COST, description="Gemini Image Generation")
async def generate_gemini_image(
    prompt: str = Form(
        ...,
        min_length=3,
        max_length=1000,
        description="A detailed description of the image to generate."
    ),
    current_user: UserSchema = Depends(get_current_api_user),
):
    """
    Generates a creative image using the Gemini service.
    """
    try:
        image_data_uri = gemini_client.generate_image(prompt=prompt)
        return {"image_data_uri": image_data_uri}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"The Image Generation service failed: {e}"
        )