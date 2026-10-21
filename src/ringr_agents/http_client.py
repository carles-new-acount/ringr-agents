"""Minimal HTTP abstraction. Requests are built for real but never sent."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    json: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Freeze the mappings so a request can't change after being built.
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))
        object.__setattr__(self, "json", MappingProxyType(dict(self.json)))

    @property
    def body(self) -> bytes:
        """Serialized body, exactly as it would go over the wire."""
        return json.dumps(dict(self.json), ensure_ascii=False).encode("utf-8")


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    json: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class HttpTransportError(Exception):
    """The request could not be delivered (timeout, connection refused...)."""


class HttpClient(ABC):
    @abstractmethod
    def send(self, request: HttpRequest) -> HttpResponse:
        """Send the request. Raises HttpTransportError if it can't be delivered."""


class FakeHttpClient(HttpClient):
    """Records the requests instead of sending them.

    By default every request gets a 200 OK, as the exercise allows assuming.
    `status_code` and `error` let tests simulate failing integrations.
    """

    def __init__(self, status_code: int = 200, error: Exception | None = None) -> None:
        self.status_code = status_code
        self.error = error
        self.sent_requests: list[HttpRequest] = []

    def send(self, request: HttpRequest) -> HttpResponse:
        logger.info("Simulated %s %s", request.method, request.url)
        if self.error is not None:
            raise self.error
        # Validate the body is serializable, as a real client would.
        _ = request.body
        self.sent_requests.append(request)
        return HttpResponse(self.status_code)
