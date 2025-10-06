from pydantic import BaseModel

class Msg(BaseModel):
    """
    A generic message schema for API responses.
    """
    msg: str