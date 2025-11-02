# app/schemas/transaction.py

from pydantic import BaseModel

class TransactionsResponse(BaseModel):
    """
    Defines the structure for a user's transaction history.
    This model is used as an API response object.
    """
    id: str
    type: str
    amount: float
    description: str
    created: str  # ISO 8601 format string

    class Config:
        """
        Pydantic configuration.
        `from_attributes = True` allows the model to be populated from ORM objects
        (like PocketBase's Record objects) that use attribute access (e.g., obj.id)
        instead of just dictionary key access (e.g., obj['id']).
        """
        from_attributes = True
