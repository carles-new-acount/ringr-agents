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


# Una petición HTTP: método (POST...), dirección, cabeceras y cuerpo JSON
@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    json: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Congelar cabeceras y cuerpo (convertirlos en solo lectura) para que
        # la petición no pueda cambiar después de construirla.
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))
        object.__setattr__(self, "json", MappingProxyType(dict(self.json)))

    @property
    def body(self) -> bytes:
        """Serialized body, exactly as it would go over the wire."""
        # El cuerpo convertido a bytes, tal cual viajaría por la red
        return json.dumps(dict(self.json), ensure_ascii=False).encode("utf-8")


# La respuesta del servidor: código de estado (200, 404...) y JSON
@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    json: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        # Cualquier código 2xx (200, 201, 204...) cuenta como éxito
        return 200 <= self.status_code < 300


# Error cuando la petición ni siquiera llega (timeout, servidor caído...)
class HttpTransportError(Exception):
    """The request could not be delivered (timeout, connection refused...)."""


# Molde de cualquier cliente HTTP: solo tiene que saber enviar una petición
class HttpClient(ABC):
    @abstractmethod
    def send(self, request: HttpRequest) -> HttpResponse:
        """Send the request. Raises HttpTransportError if it can't be delivered."""


# Cliente de mentira: NO envía nada, solo apunta las peticiones en una lista.
# Por defecto contesta 200 (OK), pero se le puede decir que falle.
class FakeHttpClient(HttpClient):
    """Records requests instead of sending them. Answers 200 unless configured otherwise."""

    def __init__(self, status_code: int = 200, error: Exception | None = None) -> None:
        self.status_code = status_code  # qué código devolverá
        self.error = error  # si se pone, simula que la red falla
        self.sent_requests: list[HttpRequest] = []  # la libreta de peticiones "enviadas"

    def send(self, request: HttpRequest) -> HttpResponse:
        logger.info("Simulated %s %s", request.method, request.url)
        # PASO 1: ¿hay que simular un fallo de red? -> lanzar el error
        if self.error is not None:
            raise self.error
        # PASO 2: convertir el cuerpo a bytes; si el JSON no es válido, falla aquí
        _ = request.body
        # PASO 3: apuntar la petición y devolver la respuesta configurada
        self.sent_requests.append(request)
        return HttpResponse(self.status_code)
