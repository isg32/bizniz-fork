# app/schemas/transaction.py

from pydantic import BaseModel

# ✅ NEW: Import the datetime type
from datetime import datetime


class TransactionsResponse(BaseModel):
    """
    Defines the structure for a user's transaction history.
    This model is used as an API response object.
    """

    id: str
    type: str
    amount: float
    description: str

    # --- FIX STARTS HERE ---
    # Change the type annotation from `str` to `datetime`.
    # FastAPI will automatically convert this to an ISO 8601 string
    # in the final JSON output, which is the standard.
    created: datetime
    # --- FIX ENDS HERE ---

    class Config:
        """
        Pydantic configuration.
        `from_attributes = True` allows the model to be populated from ORM objects
        (like PocketBase's Record objects) that use attribute access (e.g., obj.id)
        instead of just dictionary key access (e.g., obj['id']).
        """

        from_attributes = True
