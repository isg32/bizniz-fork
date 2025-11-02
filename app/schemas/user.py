# app/schemas/user.py

from pydantic import BaseModel, EmailStr, Field, model_validator
from app.core.config import settings


# --- Base schema with shared properties ---
class UserBase(BaseModel):
    email: EmailStr
    name: str | None = None


# --- Schema for creating a user (API input) ---
# This is no longer in auth.py, but here with other user schemas.
class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


# --- Main User schema for API output ---
# This is the primary model returned to the client. It never includes the password.
class User(UserBase):
    id: str
    coins: float = 0.0
    subscription_status: str | None = "inactive"
    active_plan_name: str | None = None
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    avatar: str | None = None
    verified: bool = False

    class Config:
        from_attributes = True  # Allows creating Pydantic models from ORM objects (like PocketBase records)

    @model_validator(mode="before")
    @classmethod
    def format_avatar_url(cls, data):
        """
        Ensures the avatar field is a full, valid URL if it exists.

        This validator runs before the main validation. It intercepts the raw
        data (e.g., from a PocketBase record), checks for the 'avatar' field,
        and constructs the full URL. This keeps the URL-building logic out of
        the service layer and centralizes it in the data model itself.
        """
        if isinstance(data, dict):  # For direct dict validation
            if avatar_filename := data.get("avatar"):
                collection_id = data.get("collectionId") or data.get("collection_id")
                record_id = data.get("id")
                if collection_id and record_id:
                    data["avatar"] = (
                        f"{settings.POCKETBASE_URL}/api/files/{collection_id}/{record_id}/{avatar_filename}"
                    )

        elif hasattr(data, "avatar") and data.avatar:  # For ORM-like objects
            if hasattr(data, "collection_id") and hasattr(data, "id"):
                # Check if it's not already a full URL
                if not data.avatar.startswith("http"):
                    data.avatar = f"{settings.POCKETBASE_URL}/api/files/{data.collection_id}/{data.id}/{data.avatar}"
        return data
