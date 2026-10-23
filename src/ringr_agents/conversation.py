"""Conversation history shared between the agent and the models."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    USER = "user"
    AGENT = "agent"


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


@dataclass
class Conversation:
    """Ordered list of messages exchanged in a single conversation."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    messages: list[Message] = field(default_factory=list)

    def add_user_message(self, content: str) -> None:
        self.messages.append(Message(Role.USER, content))

    def add_agent_message(self, content: str) -> None:
        self.messages.append(Message(Role.AGENT, content))

    def __len__(self) -> int:
        return len(self.messages)
