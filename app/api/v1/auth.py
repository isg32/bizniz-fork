# app/api/v1/auth.py

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field

from app.services.internal import pocketbase_service, redis_service
from app.schemas.token import Token
from app.schemas.msg import Msg
from app.schemas.user import User as UserSchema
from app.core.config import settings # Import settings for default values

router = APIRouter()

# --- Schemas for Auth API Requests ---


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: str


class EmailRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str
    password: str = Field(..., min_length=8)
    password_confirm: str


class VerificationConfirmRequest(BaseModel):
    token: str


class OAuth2CallbackRequest(BaseModel):
    code: str
    code_verifier: str
    redirect_uri: str


# --- Authentication Endpoints ---


@router.post(
    "/register",
    response_model=UserSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register_user(user_in: UserCreateRequest):
    """
    Creates a new user account.

    On success, sends a verification email and returns the new user object.
    The user will not be able to log in until their email is verified.
    """
    record, error = pocketbase_service.create_user(
        email=user_in.email, password=user_in.password, name=user_in.name
    )
    if error:
        if "validation_not_unique" in str(error):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email address already exists.",
            )
        # Log the detailed error for debugging
        print(f"Failed to create user {user_in.email}. Details: {error}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create user.", # Keep client message generic
        )

    # --- FIX STARTS HERE ---
    # The 'record' object from PocketBase's create method does not contain the email.
    # We must manually construct the response from the input data and the new record ID.
    user_data_for_response = {
        "id": record.id,
        "email": user_in.email,
        "name": user_in.name,
        "verified": record.verified,
        "coins": settings.FREE_SIGNUP_COINS,
        "subscription_status": "inactive",
        "avatar": None,
        "active_plan_name": None,
        "stripe_customer_id": None,
        "stripe_subscription_id": None,
    }

    return UserSchema.model_validate(user_data_for_response)
    # --- FIX ENDS HERE ---


@router.post("/token", response_model=Token, summary="User Login")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticates a user with email and password, returning a JWT.
    """
    auth_data = pocketbase_service.auth_with_password(
        email=form_data.username, password=form_data.password
    )
    if not auth_data or not auth_data.token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not auth_data.record.verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account not verified. Please check your email or request a new verification link.",
        )

    return {"access_token": auth_data.token, "token_type": "bearer"}


# --- Email Verification Flow ---


@router.post(
    "/verify-email/resend",
    response_model=Msg,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Resend verification email",
)
async def resend_verification_email(data: EmailRequest):
    """
    Requests a new verification email to be sent for an unverified account.
    """
    # This PocketBase SDK method doesn't return an error if the user doesn't exist or is already verified,
    # which is good for preventing email enumeration attacks.
    pb = pocketbase_service.pb
    if pb:
        pb.collection("users").request_verification(data.email)

    return {
        "msg": "If an account with that email exists and is unverified, a new verification link has been sent."
    }


@router.post(
    "/verify-email/confirm", response_model=Msg, summary="Confirm email verification"
)
async def confirm_email_verification(data: VerificationConfirmRequest):
    """
    Confirms a user's email address using the token sent to them.
    """
    success, error = pocketbase_service.confirm_verification(data.token)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email verification failed. The token may be invalid or expired. Error: {error}",
        )
    return {"msg": "Email verified successfully. You can now log in."}


# --- Password Reset Flow ---


@router.post(
    "/password/forgot",
    response_model=Msg,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request password reset",
)
async def request_password_reset(data: EmailRequest):
    """
    Requests a password reset email to be sent.
    """
    success, _ = pocketbase_service.request_password_reset(data.email)
    # Always return a success message to prevent user enumeration.
    return {
        "msg": "If an account with that email exists, a password reset link has been sent."
    }


@router.post(
    "/password/reset-confirm", response_model=Msg, summary="Confirm password reset"
)
async def confirm_password_reset(data: PasswordResetConfirmRequest):
    """
    Sets a new password using a password reset token.
    """
    if data.password != data.password_confirm:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Passwords do not match.",
        )

    success, error = pocketbase_service.confirm_password_reset(
        token=data.token, password=data.password, password_confirm=data.password_confirm
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password reset failed. The token may be invalid or expired. Error: {error}",
        )
    return {
        "msg": "Password has been reset successfully. You can now log in with your new password."
    }


# --- OAuth2 Flow for Headless API ---



@router.get("/oauth2/{provider}", summary="Get OAuth2 login URL")
async def oauth2_initiate(
    request: Request,
    provider: str,
):
    """
    Initiates the OAuth2 login flow using Redis for state.
    """
    # 1. Define the redirect_url FIRST
    # This MUST match what's in your Google/PocketBase consoles
    redirect_url = str(request.url_for("oauth2_callback", provider=provider))

    # 2. Pass the redirect_url to the service
    # (This assumes your pocketbase_service.get_oauth2_providers was updated
    # to accept and pass `redirect_url` to the SDK, as I advised before)
    try:
        providers = pocketbase_service.get_oauth2_providers()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth2 service is misconfigured.",
        )

    provider_data = next((p for p in providers if p.name == provider), None)
    if not provider_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OAuth2 provider '{provider}' not found.",
        )

    state = getattr(provider_data, "state", None)
    code_verifier = getattr(provider_data, "code_verifier", None)
    auth_url = getattr(provider_data, "auth_url", None)

    if not all([state, code_verifier, auth_url]):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth2 provider did not return all required data.",
        )

    # 3. Store the verifier in Redis, using state as the key
    stored_in_redis = await redis_service.store_oauth_state(
        state=state,
        data=code_verifier,
        expire_seconds=600  # 10 minutes
    )

    if not stored_in_redis:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Login service is temporarily unavailable. Please try again later.",
        )
    redirect_url = str(request.url_for("oauth2_callback", provider=provider))
    import urllib.parse
    auth_url = f"{provider_data.auth_url}{urllib.parse.quote(redirect_url, safe='')}"
    return {"auth_url": auth_url}



@router.get(
    "/oauth2/{provider}/callback",
    response_model=Token,
    summary="Handle OAuth2 callback",
)
async def oauth2_callback(
    request: Request,
    provider: str,
    # These come from Google's query parameters
    code: str,
    state: str,
):
    """
    The final step of the OAuth2 flow, retrieving state from Redis.
    Redirects to frontend with the access token as a query parameter.
    """
    # 1. Get the verifier from Redis using the state
    pb_verifier = await redis_service.get_oauth_state(state)

    if not pb_verifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Login session expired or is invalid. Please try logging in again.",
        )

    # 2. IMPORTANT: Delete the one-time use key
    await redis_service.delete_oauth_state(state)

    # 3. Re-create the *exact same* redirect_uri
    redirect_uri = str(request.url_for("oauth2_callback", provider=provider))

    # 4. Authenticate
    auth_data = pocketbase_service.auth_with_oauth2(
        provider=provider,
        code=code,
        code_verifier=pb_verifier,  # <-- Use the verifier from Redis
        redirect_url=redirect_uri,
    )

    if not auth_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"OAuth2 authentication with {provider} failed. The provider may have rejected the request.",
        )

    # 5. Redirect to frontend with the access token
    success_url = f"{settings.FRONTEND_BASE_URL}/auth/callback?token={auth_data.token}"
    return RedirectResponse(url=success_url)
