# app/api/v1/auth.py

from fastapi import APIRouter, Depends, HTTPException, status, Request  # Add Request
from fastapi.security import OAuth2PasswordRequestForm
from app.services.internal import pocketbase_service
from app.schemas.token import Token
from app.schemas.user import User as UserSchema  # Import UserSchema
from app.core.dependencies import (
    get_current_user_from_session,
)  # Import the new dependency

router = APIRouter()


@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticates a user and returns a PocketBase JWT token.
    (Used for third-party clients, not the Svelte app).
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
            detail="Account not verified. Please check your email.",
        )

    return {"access_token": auth_data.token, "token_type": "bearer"}


# --- ✅ NEW: Endpoint to provide the session token to the Svelte frontend ---


@router.get("/session/token", response_model=Token, summary="Get Session Token")
async def get_session_token(
    request: Request, current_user: UserSchema = Depends(get_current_user_from_session)
):
    """
    If the user has a valid session cookie, this endpoint returns the
    JWT stored within it. This is the bridge that allows the Svelte app
    to get the token it needs to authenticate with other APIs.
    """
    token = request.session.get("user_token")
    return {"access_token": token, "token_type": "bearer"}
