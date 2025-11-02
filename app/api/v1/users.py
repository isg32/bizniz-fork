# app/api/v1/users.py

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from pydantic import BaseModel, Field, EmailStr
from app.schemas.user import User as UserSchema
from app.schemas.msg import Msg
from app.core.dependencies import get_current_api_user, get_internal_api_key
from app.services.internal import pocketbase_service, email_service

router = APIRouter()

# --- Schemas for API requests ---


class UserUpdateRequest(BaseModel):
    """Defines the fields a user is allowed to update on their profile."""

    name: str | None = Field(None, description="The user's display name.")
    # email: EmailStr | None = None # Example: could be added in the future.


class BurnRequest(BaseModel):
    amount: float = Field(
        ..., gt=0, description="The positive amount of coins to burn."
    )
    description: str = Field(
        ..., description="A reason for the transaction, e.g., 'Generated an image'."
    )


class EmailRequest(BaseModel):
    subject: str
    message_html: str = Field(
        ..., description="The full HTML content of the email body."
    )


# --- Schemas for API responses ---
class BurnResponse(BaseModel):
    msg: str
    coins_burned: float
    new_coin_balance: float


class TransactionsResponse(BaseModel):
    """Defines the structure for a user's transaction history."""

    id: str
    type: str
    amount: float
    description: str
    created: str  # ISO 8601 format string


# --- API Endpoints for the Authenticated User ---


@router.get("/me", response_model=UserSchema, summary="Get current user details")
async def read_users_me(current_user: UserSchema = Depends(get_current_api_user)):
    """
    Retrieves the complete profile of the currently authenticated user.
    """
    return current_user


@router.patch("/me", response_model=UserSchema, summary="Update current user")
async def update_users_me(
    user_update: UserUpdateRequest,
    current_user: UserSchema = Depends(get_current_api_user),
):
    """
    Updates the current user's profile information (e.g., name).
    Only the fields provided in the request body will be updated.
    """
    update_data = user_update.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No update data provided."
        )

    success, updated_record_or_error = pocketbase_service.update_user(
        current_user.id, update_data
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user: {updated_record_or_error}",
        )

    return UserSchema.model_validate(updated_record_or_error)


@router.post("/me/avatar", response_model=UserSchema, summary="Upload user avatar")
async def upload_user_avatar(
    current_user: UserSchema = Depends(get_current_api_user),
    avatar_file: UploadFile = File(..., description="Image file (max 5MB, jpeg/png)."),
):
    """
    Uploads or replaces the current user's avatar.

    Accepts `multipart/form-data`.
    """
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
    ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/webp"]

    if avatar_file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed types are: {', '.join(ALLOWED_MIME_TYPES)}",
        )

    if avatar_file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File is too large. Maximum size is 5MB.",
        )

    try:
        file_content = await avatar_file.read()
        # The service layer expects a tuple: (filename, content, mime_type)
        file_tuple = (avatar_file.filename, file_content, avatar_file.content_type)
        update_data = {"avatar": file_tuple}

        success, updated_record_or_error = pocketbase_service.update_user(
            current_user.id, update_data
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update avatar: {updated_record_or_error}",
            )

        return UserSchema.model_validate(updated_record_or_error)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during file upload: {e}",
        )


@router.get(
    "/me/transactions",
    response_model=list[TransactionsResponse],
    summary="Get user transactions",
)
async def get_user_transactions(
    current_user: UserSchema = Depends(get_current_api_user),
):
    """
    Retrieves the transaction history for the authenticated user, sorted by most recent.
    """
    transactions = pocketbase_service.get_user_transactions(current_user.id)
    return [TransactionsResponse.model_validate(tx) for tx in transactions]


# --- Internal API Endpoints (requiring extra authentication) ---


@router.post(
    "/me/burn", response_model=BurnResponse, summary="Burn user coins (Internal Only)"
)
async def burn_user_coins(
    burn_data: BurnRequest,
    current_user: UserSchema = Depends(get_current_api_user),
    _: None = Depends(get_internal_api_key),
):
    """
    Securely burns coins from the authenticated user's account.

    This is a protected internal endpoint, requiring **TWO** forms of authentication:
    1. A valid User JWT Bearer token.
    2. A valid Internal API Key in the `X-Internal-API-Key` header.

    This is intended to be called by other backend services (e.g., an AI agent)
    after they have successfully performed a costly action on the user's behalf.
    """
    if (
        not getattr(current_user, "subscription_status", None)
        or current_user.subscription_status != "active"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Coin spending is only allowed with an active subscription.",
        )

    success, message = pocketbase_service.burn_coins(
        user_id=current_user.id,
        amount=burn_data.amount,
        description=burn_data.description,
    )

    if not success:
        if "Insufficient coins" in message:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=message
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to burn coins: {message}",
        )

    # Re-fetch user to get the latest coin balance
    updated_user_record = pocketbase_service.get_user_by_id(current_user.id)
    if not updated_user_record:
        # This is a fallback; should rarely happen
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve updated user balance after transaction.",
        )

    return BurnResponse(
        msg="Coins burned successfully.",
        coins_burned=burn_data.amount,
        new_coin_balance=updated_user_record.coins,
    )


@router.post(
    "/me/send-email",
    response_model=Msg,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send email to user (Internal Only)",
)
async def send_user_email(
    email_data: EmailRequest,
    current_user: UserSchema = Depends(get_current_api_user),
    _: None = Depends(get_internal_api_key),
):
    """
    Sends a general-purpose email to the authenticated user.

    This is a protected internal endpoint, requiring **TWO** forms of authentication:
    1. A valid User JWT Bearer token.
    2. A valid Internal API Key in the `X-Internal-API-Key` header.
    """
    success = email_service.send_notification_email(
        to_email=str(current_user.email),
        subject=email_data.subject,
        message_html=email_data.message_html,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is currently unavailable. The email was not sent.",
        )

    return {"msg": "Email has been accepted for delivery."}
