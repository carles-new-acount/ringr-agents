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
        self._today = today  # injectable so tests don't depend on the real date

    def build_action(self, parsed_data: Mapping[str, Any]) -> PaymentCommitment | None:
        commitment_date = self._read_field(parsed_data, "commitment_date", self._parse_commitment_date)
        committed_amount = self._read_field(parsed_data, "committed_amount", parse_positive_amount)
        if commitment_date is None or committed_amount is None:
            return None
        return PaymentCommitment(commitment_date, committed_amount)

    def _parse_commitment_date(self, value: Any) -> date:
        commitment_date = parse_iso_date(value)
        if commitment_date < self._today():
            raise InvalidFieldError(f"{commitment_date} is in the past")
        return commitment_date
