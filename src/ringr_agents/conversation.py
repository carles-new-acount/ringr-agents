"""Conversation history shared between the agent and the models."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


# Quién habla en cada mensaje: el cliente (USER) o nuestro agente (AGENT)
class Role(str, Enum):
    USER = "user"
    AGENT = "agent"


# Un mensaje suelto: quién lo dijo y qué dijo.
# frozen=True -> una vez creado no se puede modificar
@dataclass(frozen=True)
class Message:
    role: Role
    content: str


@dataclass
class Conversation:
    """Ordered list of messages exchanged in a single conversation."""

    # Identificador único de la conversación (se genera solo, al azar)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # El historial: todos los mensajes en orden, del primero al último
    messages: list[Message] = field(default_factory=list)

    # Apuntar al final del historial lo que ha dicho el cliente
    def add_user_message(self, content: str) -> None:
        self.messages.append(Message(Role.USER, content))

    # Apuntar al final del historial lo que ha respondido el agente
    def add_agent_message(self, content: str) -> None:
        self.messages.append(Message(Role.AGENT, content))

    # Permite hacer len(conversacion) para saber cuántos mensajes lleva
    def __len__(self) -> int:
        return len(self.messages)
