"""Shows what adding a new agent costs: an Action and a build_action."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ringr_agents.actions import Action
from ringr_agents.agents import ActionOutcome, BaseAgent
from ringr_agents.integrations import ActionResult, Integration
from ringr_agents.models import ConversationModel, ParserModel
from ringr_agents.validation import parse_text


@dataclass(frozen=True)
class CallbackRequest(Action):
    phone: str

    def to_payload(self) -> dict[str, Any]:
        return {"phone": self.phone}


class CallbackAgent(BaseAgent):
    def build_action(self, parsed_data: Mapping[str, Any]) -> CallbackRequest | None:
        phone = self._read_field(parsed_data, "phone", parse_text)
        return CallbackRequest(phone) if phone else None


class InMemoryQueueIntegration(Integration):
    """A non-HTTP integration: agents don't need to know the difference."""

    def __init__(self) -> None:
        self.messages: list[Action] = []

    def execute(self, action: Action, *, idempotency_key: str) -> ActionResult:
        self.messages.append(action)
        return ActionResult(success=True)


def test_new_agent_and_integration_reuse_the_whole_lifecycle():
    queue = InMemoryQueueIntegration()
    agent = CallbackAgent(
        ConversationModel(["¿A qué número?", "Le llamaremos", "Adiós"]),
        ParserModel([{"phone": None}, {"phone": "600000000"}, {"phone": "600000000"}]),
        queue,
    )

    outcomes = [agent.handle_turn("...").outcome for _ in range(3)]

    assert outcomes == [ActionOutcome.NOT_REQUIRED, ActionOutcome.EXECUTED, ActionOutcome.DUPLICATE]
    assert queue.messages == [CallbackRequest("600000000")]
