from pydantic import BaseModel


class BroadcastRequest(BaseModel):
    message: str
