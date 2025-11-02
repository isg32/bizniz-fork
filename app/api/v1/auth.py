# app/api/v1/auth.py

from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field

from app.services.internal import pocketbase_service, email_service
from app.schemas.token import Token
from app.schemas.msg import Msg
from app.schemas.user import User as UserSchema

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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create user: {error}",
        )
    return UserSchema.model_validate(record)


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


@router.get("/oauth2/providers", summary="Get available OAuth2 providers")
async def list_oauth2_providers():
    """
    Returns a list of configured OAuth2 providers.

    The frontend uses this to display "Login with..." buttons.
    It includes the `authUrl` the frontend must redirect the user to.
    """
    providers = pocketbase_service.get_oauth2_providers()
    return {"providers": providers}


@router.post(
    "/oauth2/{provider}/callback",
    response_model=Token,
    summary="Handle OAuth2 callback",
)
async def oauth2_callback(provider: str, data: OAuth2CallbackRequest):
    """
    The final step of the OAuth2 flow.

    The frontend receives a code from the provider, then sends it here.
    This endpoint exchanges the code for a user session and returns a JWT.
    """
    auth_data = pocketbase_service.auth_with_oauth2(
        provider=provider,
        code=data.code,
        code_verifier=data.code_verifier,
        redirect_url=data.redirect_uri,
    )

    if not auth_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"OAuth2 authentication with {provider} failed.",
        )

    return {"access_token": auth_data.token, "token_type": "bearer"}
