"""Chat message shape for the LLM layer — Pydantic model."""

from pydantic import BaseModel, Field


class Message(BaseModel):
    """A single turn in the LLM conversation.

    Attributes:
        role: "system", "user", or "assistant".
        content: The text content of the message.
    """

    role: str = Field(
        ...,
        pattern="^(system|user|assistant)$",
        description="Role of the message sender.",
    )
    content: str = Field(default="", description="Text content of the message.")

    def to_openai_dict(self) -> dict:
        """Serialize to the dict shape the OpenAI SDK expects."""
        return {"role": self.role, "content": self.content}
