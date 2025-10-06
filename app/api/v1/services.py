from fastapi import APIRouter, Depends, HTTPException, status, Body
from app.core.dependencies import get_current_api_user
from app.schemas.user import User as UserSchema
from app.services import gemini_service, pocketbase_service

router = APIRouter()

@router.post("/chat")
async def chat_with_ai(
    prompt: str = Body(..., embed=True, min_length=1, max_length=2000),
    current_user: UserSchema = Depends(get_current_api_user)
):
    """
    Handles chat requests to the Gemini service.
    This is a protected endpoint that costs coins to use.
    
    Example Request Body:
    {
        "prompt": "What is the capital of France?"
    }
    """
    COIN_COST = 1.0

    user_record = pocketbase_service.get_user_by_id(current_user.id)
    if not user_record or user_record.coins < COIN_COST:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient coins. This action requires {COIN_COST} coins, but you have {user_record.coins if user_record else 0}."
        )

    ai_response = gemini_service.generate_chat_response(prompt)
    if not ai_response:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI service is currently unavailable or failed to generate a response. You have not been charged."
        )

    success, message = pocketbase_service.burn_coins(current_user.id, COIN_COST)
    if not success:
        print(f"CRITICAL: FAILED to burn {COIN_COST} coins for user {current_user.id} after successful AI call. Reason: {message}")

    updated_user_record = pocketbase_service.get_user_by_id(current_user.id)
    
    return {
        "response": ai_response,
        "coins_burned": COIN_COST,
        "new_coin_balance": updated_user_record.coins if updated_user_record else "unknown"
    }