# app/core/dependencies.py

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from app.services.internal import pocketbase_service
from app.schemas.user import User as UserSchema
from app.core.config import settings

# This tells FastAPI that the user's Bearer token is expected at the `/api/v1/auth/token` endpoint.
# It defines the scheme for the auto-generated API documentation.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def get_current_api_user(token: str = Depends(oauth2_scheme)) -> UserSchema:
    """
    Dependency to get the current user from a PocketBase JWT Bearer token.

    This is the primary way to protect API endpoints. It validates the token
    and returns the corresponding user record.
    """
    user_record = pocketbase_service.get_user_from_token(token)
    if not user_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Convert the raw PocketBase record to our Pydantic User schema for type safety and consistency.
    return UserSchema.model_validate(user_record)


def get_internal_api_key(x_internal_api_key: str = Header(...)):
    """
    Dependency to protect internal-only endpoints (e.g., coin burn).

    It checks for a secret token in the 'X-Internal-API-Key' header. This provides
    a second layer of security for sensitive operations, ensuring they can't be
    triggered by a compromised user token alone.
    """
    if x_internal_api_key != settings.INTERNAL_API_SECRET_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Internal API Key",
        )


# --- REMOVED ---
# The get_current_user_from_session dependency has been completely removed as it
# relied on server-side session cookies, which are not used in a pure API.
