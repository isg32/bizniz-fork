# app/schemas/token.py

from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str


class GoogleLoginRequest(BaseModel):
    id_token: str


# Note: The TokenData schema was previously used for decoding,
# but since that logic is handled internally by the pocketbase_service,
# it's not strictly necessary for the API's public contract and can be removed for simplicity.
