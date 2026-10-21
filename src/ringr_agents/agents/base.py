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


class ActionOutcome(str, Enum):
    NOT_REQUIRED = "not_required"  # conditions not met yet
    DUPLICATE = "duplicate"  # already executed in this conversation
    EXECUTED = "executed"
    FAILED = "failed"  # will be retried if still required next turn


@dataclass(frozen=True)
class TurnResult:
    reply: str
    parsed_data: Mapping[str, Any]
    action: Action | None
    outcome: ActionOutcome
    action_result: ActionResult | None = None


class BaseAgent(ABC):
    """Template Method: `handle_turn` fixes the order of the steps and each
    agent only decides which action (if any) the parsed data leads to.

    One instance handles one conversation: the deduplication state lives here.
    """

    def __init__(
        self,
        conversation_model: SupportsAnswerUser,
        parser_model: SupportsParseData,
        integration: Integration,
        conversation: Conversation | None = None,
    ) -> None:
        self._conversation_model = conversation_model
        self._parser_model = parser_model
        self._integration = integration
        self._conversation = conversation if conversation is not None else Conversation()
        self._executed_actions: set[Action] = set()

    @property
    def conversation(self) -> Conversation:
        return self._conversation

    def handle_turn(self, user_message: str) -> TurnResult:
        self._conversation.add_user_message(user_message)

        reply = self._conversation_model.answer_user(self._conversation)
        self._conversation.add_agent_message(reply)

        parsed_data = self._parser_model.parse_data(self._conversation)
        action = self.build_action(parsed_data)

        if action is None:
            return TurnResult(reply, parsed_data, None, ActionOutcome.NOT_REQUIRED)
        if self._is_duplicate(action):
            logger.debug("Skipping duplicate %r", action)
            return TurnResult(reply, parsed_data, action, ActionOutcome.DUPLICATE)

        result = self._integration.execute(action, idempotency_key=idempotency_key(self._conversation.id, action))
        if not result.success:
            return TurnResult(reply, parsed_data, action, ActionOutcome.FAILED, result)

        # Only successful actions count: a failed one is retried in a later turn.
        self._executed_actions.add(action)
        return TurnResult(reply, parsed_data, action, ActionOutcome.EXECUTED, result)

    @abstractmethod
    def build_action(self, parsed_data: Mapping[str, Any]) -> Action | None:
        """Validate and normalize the parsed data and return the action to
        execute, or None if the business conditions are not met."""

    def _is_duplicate(self, action: Action) -> bool:
        """Same action with the same normalized data already executed in this
        conversation. Override for stricter policies (e.g. one action per conversation)."""
        return action in self._executed_actions

    def _read_field(self, parsed_data: Mapping[str, Any], name: str, parse: Callable[[Any], T]) -> T | None:
        """Missing, null or invalid values are all treated as "not provided":
        an invalid value must never trigger an action."""
        value = parsed_data.get(name)
        if value is None:
            return None
        try:
            return parse(value)
        except InvalidFieldError as exc:
            logger.warning("%s: ignoring invalid %s: %s", type(self).__name__, name, exc)
            return None
