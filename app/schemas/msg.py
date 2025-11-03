# app/schemas/msg.py

from pydantic import BaseModel


class Msg(BaseModel):
    """A generic message schema for simple API responses."""

    msg: str
