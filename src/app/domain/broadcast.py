from pydantic import BaseModel


class BroadcastRequest(BaseModel):
    """
    DTO для HTTP-запроса /broadcast.
    """
    message: str
