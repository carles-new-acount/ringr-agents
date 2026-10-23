"""Common turn lifecycle shared by every agent."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeVar

from ringr_agents.actions import Action, idempotency_key
from ringr_agents.conversation import Conversation
from ringr_agents.integrations import ActionResult, Integration
from ringr_agents.models import SupportsAnswerUser, SupportsParseData
from ringr_agents.validation import InvalidFieldError

logger = logging.getLogger(__name__)

T = TypeVar("T")


# Las 4 cosas que pueden pasar con la acción al final de un turno
class ActionOutcome(str, Enum):
    NOT_REQUIRED = "not_required"  # todavía faltan datos, no hay nada que enviar
    DUPLICATE = "duplicate"  # ya se envió esto mismo en esta conversación
    EXECUTED = "executed"  # enviado y aceptado
    FAILED = "failed"  # el envío falló; se reintentará si el turno siguiente sigue pidiéndolo


# Todo lo que devuelve un turno: qué respondió el agente, la ficha que sacó
# la IA, la acción decidida, qué pasó con ella y la respuesta de la API.
@dataclass(frozen=True)
class TurnResult:
    reply: str
    parsed_data: Mapping[str, Any]
    action: Action | None
    outcome: ActionOutcome
    action_result: ActionResult | None = None


# Molde común de todos los agentes. Aquí está el "paso a paso" de cada turno;
# cada agente concreto solo decide qué acción construir (build_action).
class BaseAgent(ABC):
    """Runs a conversation turn. One instance handles one conversation."""

    def __init__(
        self,
        conversation_model: SupportsAnswerUser,
        parser_model: SupportsParseData,
        integration: Integration,
        conversation: Conversation | None = None,
    ) -> None:
        self._conversation_model = conversation_model  # la IA que contesta
        self._parser_model = parser_model  # la IA que rellena la ficha
        self._integration = integration  # por dónde se envía la acción
        # La conversación: si no se pasa una, se empieza una nueva vacía
        self._conversation = conversation if conversation is not None else Conversation()
        # La libreta de "ya enviado": acciones que salieron bien en esta conversación
        self._executed_actions: set[Action] = set()

    # Permite leer la conversación desde fuera (agent.conversation)
    @property
    def conversation(self) -> Conversation:
        return self._conversation

    def handle_turn(self, user_message: str) -> TurnResult:
        # PASO 1: apuntar lo que dijo el cliente
        self._conversation.add_user_message(user_message)

        # PASO 2: la IA responde, y se apunta la respuesta
        reply = self._conversation_model.answer_user(self._conversation)
        self._conversation.add_agent_message(reply)

        # PASO 3: la otra IA lee toda la conversación y da la ficha
        parsed_data = self._parser_model.parse_data(self._conversation)

        # PASO 4: convertir la ficha en una acción (o None si faltan datos)
        action = self.build_action(parsed_data)

        # PASO 5: decidir
        if action is None:  # ¿faltan datos?
            return TurnResult(reply, parsed_data, None, ActionOutcome.NOT_REQUIRED)
        if self._is_duplicate(action):  # ¿ya se envió?
            logger.debug("Skipping duplicate %r", action)
            return TurnResult(reply, parsed_data, action, ActionOutcome.DUPLICATE)

        # PASO 6: enviar (con su clave de idempotencia para que el servidor detecte reenvíos)
        result = self._integration.execute(action, idempotency_key=idempotency_key(self._conversation.id, action))
        if not result.success:  # ¿falló el envío?
            return TurnResult(reply, parsed_data, action, ActionOutcome.FAILED, result)

        # PASO 7: apuntar en la libreta de "ya enviado". Solo se apuntan las que
        # salen bien: una que falla se volverá a intentar en un turno posterior.
        self._executed_actions.add(action)
        return TurnResult(reply, parsed_data, action, ActionOutcome.EXECUTED, result)

    # Cada agente concreto (DebtAgent, AssistanceAgent...) rellena esto:
    # mira la ficha y devuelve la acción, o None si aún no se puede hacer.
    @abstractmethod
    def build_action(self, parsed_data: Mapping[str, Any]) -> Action | None:
        """Return the action to execute, or None if the conditions are not met."""

    # ¿Está esta acción exacta (mismos datos) ya en la libreta de "ya enviado"?
    def _is_duplicate(self, action: Action) -> bool:
        """Whether this exact action was already executed in this conversation."""
        return action in self._executed_actions

    # Leer un campo de la ficha y validarlo con la función `parse` que se le pase.
    # Si falta, es nulo o es inválido -> None (como si el cliente no lo hubiera dicho).
    def _read_field(self, parsed_data: Mapping[str, Any], name: str, parse: Callable[[Any], T]) -> T | None:
        """Read a field, treating missing, null or invalid values as not provided."""
        # PASO 1: coger el valor; si no está o es nulo, no hay dato
        value = parsed_data.get(name)
        if value is None:
            return None
        # PASO 2: validarlo; si es inválido, se avisa en el log y se ignora
        try:
            return parse(value)
        except InvalidFieldError as exc:
            logger.warning("%s: ignoring invalid %s: %s", type(self).__name__, name, exc)
            return None
