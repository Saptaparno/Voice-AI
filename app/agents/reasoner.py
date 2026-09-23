"""Reasoner agent — LLM chat with rolling conversation history."""

from app.config import MAX_HISTORY_TURNS, SYSTEM_PROMPT
from app.models import Message
from app.services import ask_model


# Exit-trigger phrases — substring-matched, lowercased.
_EXIT_PHRASES = frozenset({
    "exit", "quit", "stop", "goodbye", "bye", "good bye",
    "shut down", "that's all", "thats all", "end the session",
})


class ConversationHistory:
    """Rolling LLM context window.

    Maintains a list of Messages starting with the system prompt.
    ``MAX_HISTORY_TURNS`` controls how many user+assistant pairs are kept
    (excluding the system message).
    """

    def __init__(self):
        self._messages: list[Message] = [Message(role="system", content=SYSTEM_PROMPT)]

    def add_user(self, text: str):
        self._messages.append(Message(role="user", content=text))
        self._trim()

    def add_assistant(self, text: str):
        self._messages.append(Message(role="assistant", content=text))
        self._trim()

    def to_list(self) -> list[dict]:
        return [m.to_openai_dict() for m in self._messages]

    def _trim(self):
        # Keep system message + the last 2*MAX_HISTORY_TURNS messages.
        keep = 2 * MAX_HISTORY_TURNS
        if len(self._messages) > keep + 1:
            self._messages = [self._messages[0]] + self._messages[-keep:]

    def is_exit(self, text: str) -> bool:
        """Return True if ``text`` contains an exit phrase."""
        t = text.lower().strip().rstrip(".!?")
        if t in _EXIT_PHRASES:
            return True
        return any(phrase in t for phrase in _EXIT_PHRASES)


def ask(text: str, history: ConversationHistory):
    """Add ``text`` to history, call the LLM, append the reply, return reply."""
    history.add_user(text)
    result = ask_model(history.to_list())
    history.add_assistant(result.text)
    return result
