from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ringr_agents.actions import AssistanceRequest
from ringr_agents.agents.base import BaseAgent
from ringr_agents.validation import parse_text


# Agente de asistencia: cuando el cliente pide algo que tiene que resolver
# una persona, registra la solicitud para un agente humano.
class AssistanceAgent(BaseAgent):
    """Answers questions and registers requests to be handled by a human."""

    def build_action(self, parsed_data: Mapping[str, Any]) -> AssistanceRequest | None:
        # PASO 1: leer y limpiar el texto de la solicitud
        request = self._read_field(parsed_data, "request", parse_text)
        # PASO 2: si no hay solicitud, no hay nada que registrar
        if request is None:
            return None
        # PASO 3: hay solicitud -> crear la acción
        return AssistanceRequest(request)
