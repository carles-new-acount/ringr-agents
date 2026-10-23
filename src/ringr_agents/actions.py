"""Actions an agent can decide to execute."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any


# Molde común de todas las acciones: cada acción tiene que saber
# convertirse en el JSON (payload) que se manda a la API.
class Action(ABC):
    """Validated data to send to an integration. Subclasses are frozen dataclasses."""

    @abstractmethod
    def to_payload(self) -> dict[str, Any]: ...


# Acción del DebtAgent: "el cliente se compromete a pagar X € el día Y".
# frozen=True -> no se puede modificar y se puede comparar/guardar en un set
# (eso es lo que permite detectar duplicados).
@dataclass(frozen=True)
class PaymentCommitment(Action):
    commitment_date: date
    committed_amount: float

    def to_payload(self) -> dict[str, Any]:
        # La fecha se manda como texto 'aaaa-mm-dd'
        return {
            "commitment_date": self.commitment_date.isoformat(),
            "committed_amount": self.committed_amount,
        }


# Acción del AssistanceAgent: "el cliente pide esto a un agente humano"
@dataclass(frozen=True)
class AssistanceRequest(Action):
    request: str

    def to_payload(self) -> dict[str, Any]:
        return {"request": self.request}


# Genera una "huella" única para cada envío: misma conversación + misma acción
# + mismos datos = misma clave. Si se reenvía por error, el servidor ve la
# misma clave y sabe que ya lo tenía, así no lo registra dos veces.
def idempotency_key(conversation_id: str, action: Action) -> str:
    """Deterministic key so the server can discard retried requests."""
    # PASO 1: juntar todo en un texto JSON (sort_keys -> siempre en el mismo orden)
    raw = json.dumps(
        {"conversation": conversation_id, "action": type(action).__name__, "payload": action.to_payload()},
        sort_keys=True,
    )
    # PASO 2: pasarlo por SHA-256 para obtener una clave corta y fija
    return hashlib.sha256(raw.encode()).hexdigest()
