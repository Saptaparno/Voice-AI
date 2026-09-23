"""Sarvam-105B via the OpenAI-compatible endpoint."""

import os
from dataclasses import dataclass

from openai import OpenAI

from app.config import OPENAI_API_KEY, OPENAI_BASE_URL, SARVAM_CHAT_MODEL


_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        _client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    return _client


@dataclass
class ChatResult:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


def ask_model(messages: list[dict]) -> ChatResult:
    """Send a message list to Sarvam-105B and return the text reply.

    ``messages`` must be a list of dicts with ``"role"`` and ``"content"``
    keys (OpenAI chat format).  A ``"system"`` message is typically included
    as the first item.

    The ``reasoning_effort: null`` extra_body suppresses the model's internal
    thinking/reasoning tokens so the visible reply is produced faster and
    costs fewer output tokens.
    """
    client = _get_client()
    try:
        response = client.chat.completions.create(
            model=SARVAM_CHAT_MODEL,
            messages=messages,
            temperature=0,
            max_tokens=128,
            extra_body={"reasoning_effort": None},
        )
        usage = response.usage
        return ChatResult(
            text=(response.choices[0].message.content or "").strip(),
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            total_tokens=getattr(usage, "total_tokens", 0) or 0,
        )
    except Exception as e:
        return ChatResult(text=f"Sorry, I had trouble processing that: {e}")
