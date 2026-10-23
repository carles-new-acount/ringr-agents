from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

from ringr_agents.actions import PaymentCommitment
from ringr_agents.agents.base import BaseAgent
from ringr_agents.conversation import Conversation
from ringr_agents.integrations import Integration
from ringr_agents.models import SupportsAnswerUser, SupportsParseData
from ringr_agents.validation import InvalidFieldError, parse_iso_date, parse_positive_amount


# Agente de deudas: cuando el cliente da fecha Y cantidad, registra el compromiso de pago
class DebtAgent(BaseAgent):
    """Registers payment commitments for outstanding debts."""

    def __init__(
        self,
        conversation_model: SupportsAnswerUser,
        parser_model: SupportsParseData,
        integration: Integration,
        conversation: Conversation | None = None,
        today: Callable[[], date] = date.today,
    ) -> None:
        super().__init__(conversation_model, parser_model, integration, conversation)
        # El "reloj": función que dice qué día es hoy. Se puede cambiar en los
        # tests para que no dependan de la fecha real.
        self._today = today

    def build_action(self, parsed_data: Mapping[str, Any]) -> PaymentCommitment | None:
        # PASO 1: leer y validar la fecha (formato correcto y no en el pasado)
        commitment_date = self._read_field(parsed_data, "commitment_date", self._parse_commitment_date)
        # PASO 2: leer y validar la cantidad (número positivo)
        committed_amount = self._read_field(parsed_data, "committed_amount", parse_positive_amount)
        # PASO 3: si falta cualquiera de las dos, todavía no hay compromiso
        if commitment_date is None or committed_amount is None:
            return None
        # PASO 4: están las dos -> crear la acción
        return PaymentCommitment(commitment_date, committed_amount)

    # Validar la fecha: formato 'aaaa-mm-dd' y que no sea anterior a hoy
    def _parse_commitment_date(self, value: Any) -> date:
        commitment_date = parse_iso_date(value)
        if commitment_date < self._today():
            raise InvalidFieldError(f"{commitment_date} is in the past")
        return commitment_date
