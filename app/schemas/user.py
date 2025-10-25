# app/schemas/user.py

from pydantic import BaseModel, EmailStr

# --- Properties shared by all user models ---
class UserBase(BaseModel):
    email: EmailStr
    name: str | None = None

# --- Properties for creating a new user (used by the API) ---
class UserCreate(UserBase):
    password: str

# --- Properties returned to the client (never include the password!) ---
class User(UserBase):
    id: str
    coins: float = 0.0
    subscription_status: str = "inactive"
    
    # --- NEW: Add optional avatar URL field ---
    avatar: str | None = None

    class Config:
        from_attributes = True # Pydantic v2 replaces orm_mode