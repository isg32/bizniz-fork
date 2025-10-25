# app/core/dependencies.py

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from app.services.internal import pocketbase_service
from app.schemas.user import User as UserSchema
from app.core.config import settings

# This tells FastAPI where to look for the user's Bearer token in the request
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def get_current_api_user(token: str = Depends(oauth2_scheme)) -> UserSchema:
    """
    Dependency to get the current user from a PocketBase auth token.
    This protects API endpoints against unauthorized user access.
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


# --- NEW: Dependency for Internal Service Authentication ---

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