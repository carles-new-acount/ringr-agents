"""Simulated language models.

In production these would wrap an LLM call. Here they return pre-scripted
outputs, one per turn, so the agents can be exercised deterministically.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from ringr_agents.conversation import Conversation


class SupportsAnswerUser(Protocol):
    """Anything able to produce the agent's reply (a real LLM client, a mock...)."""

    def answer_user(self, conversation: Conversation) -> str: ...


class SupportsParseData(Protocol):
    """Anything able to extract structured data from the conversation."""

    def parse_data(self, conversation: Conversation) -> dict[str, Any]: ...


class ScriptExhaustedError(RuntimeError):
    """Raised when a simulated model is asked for more turns than it was scripted for."""


class _ScriptedModel:
    """Returns the next scripted output on each call."""

    def __init__(self, outputs: Iterable[Any]) -> None:
        self._outputs = list(outputs)
        self._turn = 0

    def _next_output(self) -> Any:
        if self._turn >= len(self._outputs):
            raise ScriptExhaustedError(
                f"{type(self).__name__} was scripted for {len(self._outputs)} turns "
                f"but turn {self._turn + 1} was requested"
            )
        output = self._outputs[self._turn]
        self._turn += 1
        return output


class ConversationModel(_ScriptedModel):
    """Generates the agent's reply to the user."""

    def __init__(self, replies: Iterable[str]) -> None:
        super().__init__(replies)

    def answer_user(self, conversation: Conversation) -> str:
        return self._next_output()


class ParserModel(_ScriptedModel):
    """Extracts structured data from the conversation.

    Each output is the data extracted from the whole conversation so far,
    not only from the last message.
    """

    def __init__(self, parsed_outputs: Iterable[dict[str, Any]]) -> None:
        super().__init__(parsed_outputs)

    def parse_data(self, conversation: Conversation) -> dict[str, Any]:
        # Copy so callers can't mutate the script.
        return dict(self._next_output())
