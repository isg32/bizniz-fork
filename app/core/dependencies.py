# app/core/dependencies.py

from fastapi import Depends, HTTPException, status, Header, Request  # Add Request
from fastapi.security import OAuth2PasswordBearer
from app.services.internal import pocketbase_service
from app.schemas.user import User as UserSchema
from app.core.config import settings

# This tells FastAPI where to look for the user's Bearer token in the request
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def get_current_api_user(token: str = Depends(oauth2_scheme)) -> UserSchema:
    """
    Dependency to get the current user from a PocketBase auth token.
    This protects API endpoints against unauthorized user access via Bearer Token.
    """
    user_record = pocketbase_service.get_user_from_token(token)
    if not user_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Convert the PocketBase record to our Pydantic User schema for type safety
    return UserSchema.model_validate(user_record)


def get_internal_api_key(x_internal_api_key: str = Header(...)):
    """
    Dependency to protect internal-only endpoints.
    Checks for a secret token in the 'X-Internal-API-Key' header.
    """
    if x_internal_api_key != settings.INTERNAL_API_SECRET_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Internal API Key",
        )


# --- ✅ NEW: Dependency for Web Session Authentication ---


def get_current_user_from_session(request: Request) -> UserSchema:
    """
    Dependency to get the current user from the web session cookie.
    This protects API endpoints for the SvelteKit frontend.
    """
    token = request.session.get("user_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user_record = pocketbase_service.get_user_from_token(token)
    if not user_record:
        # The token in the session is invalid or expired, clear the session
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )

    return UserSchema.model_validate(user_record)
