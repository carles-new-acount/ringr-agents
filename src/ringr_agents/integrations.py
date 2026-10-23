"""Integrations: deliver an Action to an external system."""

from __future__ import annotations

import logging
import string
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from urllib.parse import quote

from ringr_agents.actions import Action
from ringr_agents.http_client import HttpClient, HttpRequest, HttpTransportError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActionResult:
    success: bool
    status_code: int | None = None
    error: str | None = None


class Integration(ABC):
    @abstractmethod
    def execute(self, action: Action, *, idempotency_key: str) -> ActionResult:
        """Deliver the action. Delivery problems are returned, not raised."""


class Authenticator(ABC):
    @abstractmethod
    def auth_headers(self) -> dict[str, str]: ...


@dataclass(frozen=True)
class BearerTokenAuth(Authenticator):
    token: str = field(repr=False)  # keep the secret out of logs and tracebacks

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


_HEADER_SAFE_CHARS = "".join(c for c in string.printable if c not in "%\t\n\r\x0b\x0c")


def to_header_value(value: object) -> str:
    """Percent-encode anything that is not printable ASCII (also prevents header injection)."""
    return quote(str(value), safe=_HEADER_SAFE_CHARS)


class HttpIntegration(Integration):
    """Sends the action as a JSON POST; non-null payload fields are also sent as headers."""

    def __init__(self, url: str, client: HttpClient, auth: Authenticator, method: str = "POST") -> None:
        self._url = url
        self._client = client
        self._auth = auth
        self._method = method

    def build_request(self, action: Action, *, idempotency_key: str) -> HttpRequest:
        payload = action.to_payload()
        headers = {name: to_header_value(value) for name, value in payload.items() if value is not None}
        # Fixed headers go last so payload data can never overwrite them.
        headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Idempotency-Key": idempotency_key,
                **self._auth.auth_headers(),
            }
        )
        return HttpRequest(method=self._method, url=self._url, headers=headers, json=payload)

    def execute(self, action: Action, *, idempotency_key: str) -> ActionResult:
        request = self.build_request(action, idempotency_key=idempotency_key)
        try:
            response = self._client.send(request)
        except HttpTransportError as exc:
            logger.warning("Could not deliver %s to %s: %s", type(action).__name__, self._url, exc)
            return ActionResult(success=False, error=str(exc))
        if not response.ok:
            logger.warning("%s rejected %s with status %s", self._url, type(action).__name__, response.status_code)
            return ActionResult(success=False, status_code=response.status_code)
        return ActionResult(success=True, status_code=response.status_code)
