"""Actions an agent can decide to execute against an external system.

An action only describes *what* to do with already validated data. *How* it is
delivered (HTTP, queue, ...) is the responsibility of an Integration.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any


class Action(ABC):
    """Base class for actions. Subclasses must be frozen dataclasses so that
    two actions with the same data are equal and hashable (used for dedup)."""

    @abstractmethod
    def to_payload(self) -> dict[str, Any]:
        """JSON-serializable data, keyed by the same names the ParserModel uses."""


@dataclass(frozen=True)
class PaymentCommitment(Action):
    commitment_date: date
    committed_amount: float

    def to_payload(self) -> dict[str, Any]:
        return {
            "commitment_date": self.commitment_date.isoformat(),
            "committed_amount": self.committed_amount,
        }


@dataclass(frozen=True)
class AssistanceRequest(Action):
    request: str

    def to_payload(self) -> dict[str, Any]:
        return {"request": self.request}


def idempotency_key(conversation_id: str, action: Action) -> str:
    """Deterministic key so the server can also discard duplicates (e.g. a retry
    after a timeout where the first request did reach the server)."""
    raw = json.dumps(
        {"conversation": conversation_id, "action": type(action).__name__, "payload": action.to_payload()},
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()
