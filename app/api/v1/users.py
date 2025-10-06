
from fastapi import APIRouter, Depends
from app.schemas.user import User
from app.core.dependencies import get_current_api_user

router = APIRouter()

@router.get("/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_api_user)):
    """
    Get the details of the currently authenticated user.
    """
    return current_user
