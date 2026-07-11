from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    suggestions: list[str] = Field(default_factory=list)
