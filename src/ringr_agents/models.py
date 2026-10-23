"""Simulated models that return one scripted output per turn."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from ringr_agents.conversation import Conversation


# "Contrato" de la IA que contesta: vale cualquier objeto que tenga
# un método answer_user(conversacion) -> texto. Así mañana se puede
# enchufar una IA real sin tocar el agente.
class SupportsAnswerUser(Protocol):
    """Anything able to produce the agent's reply (a real LLM client, a mock...)."""

    def answer_user(self, conversation: Conversation) -> str: ...


# "Contrato" de la IA que rellena la ficha: vale cualquier objeto que tenga
# un método parse_data(conversacion) -> diccionario con los datos.
class SupportsParseData(Protocol):
    """Anything able to extract structured data from the conversation."""

    def parse_data(self, conversation: Conversation) -> dict[str, Any]: ...


# Error que salta si le pedimos a la IA simulada más turnos de los que tiene en el guion
class ScriptExhaustedError(RuntimeError):
    """Raised when a simulated model is asked for more turns than it was scripted for."""


# Base de las IAs simuladas: tienen un "guion" (lista de respuestas)
# y en cada llamada devuelven la siguiente.
class _ScriptedModel:
    """Returns the next scripted output on each call."""

    def __init__(self, outputs: Iterable[Any]) -> None:
        self._outputs = list(outputs)  # el guion completo
        self._turn = 0  # por qué turno del guion vamos

    def _next_output(self) -> Any:
        # ¿Se acabó el guion? -> error claro en vez de un IndexError raro
        if self._turn >= len(self._outputs):
            raise ScriptExhaustedError(
                f"{type(self).__name__} was scripted for {len(self._outputs)} turns "
                f"but turn {self._turn + 1} was requested"
            )
        # Coger la respuesta de este turno y avanzar al siguiente
        output = self._outputs[self._turn]
        self._turn += 1
        return output


# IA simulada que CONTESTA al cliente (devuelve texto)
class ConversationModel(_ScriptedModel):
    """Generates the agent's reply to the user."""

    def __init__(self, replies: Iterable[str]) -> None:
        super().__init__(replies)

    def answer_user(self, conversation: Conversation) -> str:
        # No mira la conversación: simplemente lee la siguiente línea del guion
        return self._next_output()


# IA simulada que RELLENA LA FICHA (devuelve un diccionario con los datos)
class ParserModel(_ScriptedModel):
    """Extracts structured data from the whole conversation so far."""

    def __init__(self, parsed_outputs: Iterable[dict[str, Any]]) -> None:
        super().__init__(parsed_outputs)

    def parse_data(self, conversation: Conversation) -> dict[str, Any]:
        # Se devuelve una copia para que nadie pueda modificar el guion desde fuera
        return dict(self._next_output())
