from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from app.services.internal import pocketbase_service
from app.schemas.token import Token

router = APIRouter()

@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    Authenticates a user and returns a PocketBase JWT token.
    Your apps should call this endpoint first.
    """
    auth_data = pocketbase_service.auth_with_password(
        email=form_data.username,  # OAuth2 spec uses 'username' for the email field
        password=form_data.password
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