# app/api/v1/users.py

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from pydantic import BaseModel, Field
from app.schemas.user import User
from app.core.dependencies import get_current_api_user, get_internal_api_key
from app.services.internal import pocketbase_service, email_service

router = APIRouter()

# --- Schemas for new endpoints ---

class BurnRequest(BaseModel):
    amount: float = Field(..., gt=0, description="The amount of coins to burn. Must be positive.")
    description: str

class BurnResponse(BaseModel):
    msg: str
    coins_burned: float
    new_coin_balance: float

class EmailRequest(BaseModel):
    subject: str
    message_html: str = Field(..., description="The full HTML content of the email body.")


# --- API Endpoints ---

@router.get("/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_api_user)):
    """
    Get the details of the currently authenticated user, including their avatar URL.
    """
    return current_user


@router.post("/me/avatar", response_model=User)
async def upload_user_avatar(
    current_user: User = Depends(get_current_api_user),
    avatar_file: UploadFile = File(...)
):
    """
    Uploads or updates the current user's avatar.
    Accepts multipart/form-data with a file named 'avatar_file'. Max size: 5MB.
    """
    if not avatar_file.content_type.startswith("image/"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid file type. Please upload an image.")

    if avatar_file.size > 5 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is too large. Maximum size is 5MB.")

    try:
        file_content = await avatar_file.read()
        file_tuple = (avatar_file.filename, file_content, avatar_file.content_type)
        update_data = {"avatar": file_tuple}

        success, updated_record_or_error = pocketbase_service.update_user(current_user.id, update_data)

        if not success:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to update avatar: {updated_record_or_error}")
        
        return User.model_validate(updated_record_or_error)
    except Exception as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"An unexpected error occurred: {e}")


@router.post("/me/burn", response_model=BurnResponse, summary="Burn User Coins (Internal)")
async def burn_user_coins(
    burn_data: BurnRequest,
    current_user: User = Depends(get_current_api_user),
    _: None = Depends(get_internal_api_key)
):
    """
    Securely burns coins from the authenticated user's account.

    Requires **TWO** forms of authentication:
    1. A valid User Bearer token.
    2. A valid Internal API Key in the `X-Internal-API-Key` header.
    """
    success, message = pocketbase_service.burn_coins(
        user_id=current_user.id, amount=burn_data.amount, description=burn_data.description
    )

    if not success:
        if "Insufficient coins" in message:
            raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, message)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Failed to burn coins: {message}")
    
    updated_user_record = pocketbase_service.get_user_by_id(current_user.id)
    if not updated_user_record:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not retrieve updated balance.")

    return BurnResponse(
        msg="Coins burned successfully.",
        coins_burned=burn_data.amount,
        new_coin_balance=updated_user_record.coins
    )


@router.post("/me/send-email", status_code=status.HTTP_202_ACCEPTED, summary="Send User Email (Internal)")
async def send_user_email(
    email_data: EmailRequest,
    current_user: User = Depends(get_current_api_user),
    _: None = Depends(get_internal_api_key)
):
    """
    Sends a general-purpose email to the authenticated user.

    Requires **TWO** forms of authentication:
    1. A valid User Bearer token.
    2. A valid Internal API Key in the `X-Internal-API-Key` header.
    """
    success = email_service.send_notification_email(
        to_email=current_user.email,
        subject=email_data.subject,
        message_html=email_data.message_html
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is currently unavailable. The email was not sent."
        )
    
    return {"msg": "Email has been accepted for delivery."}