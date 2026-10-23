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


# Cómo ha ido el envío: si salió bien, qué código devolvió el servidor
# y, si falló, el motivo.
@dataclass(frozen=True)
class ActionResult:
    success: bool
    status_code: int | None = None
    error: str | None = None


# Molde de cualquier integración (HTTP, cola de mensajes, email...):
# recibe una acción y la entrega. Si algo falla, lo DEVUELVE en el resultado,
# no lanza excepción, para que el agente no se caiga.
class Integration(ABC):
    @abstractmethod
    def execute(self, action: Action, *, idempotency_key: str) -> ActionResult:
        """Deliver the action. Delivery problems are returned, not raised."""


# Molde de cualquier forma de autenticarse: devuelve las cabeceras a añadir
class Authenticator(ABC):
    @abstractmethod
    def auth_headers(self) -> dict[str, str]: ...


# Autenticación con token: añade la cabecera "Authorization: Bearer <token>"
@dataclass(frozen=True)
class BearerTokenAuth(Authenticator):
    token: str = field(repr=False)  # repr=False -> el token no sale al imprimir el objeto ni en logs

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


# Caracteres que se pueden poner tal cual en una cabecera: ASCII imprimible
# menos '%' y los saltos de línea/tabuladores.
_HEADER_SAFE_CHARS = "".join(c for c in string.printable if c not in "%\t\n\r\x0b\x0c")


# Convertir cualquier valor en texto apto para cabecera HTTP. Lo que no es
# seguro (tildes, €, saltos de línea...) se codifica como %XX. Así nadie puede
# colar cabeceras falsas metiendo un salto de línea en el dato.
def to_header_value(value: object) -> str:
    """Percent-encode anything that is not printable ASCII (also prevents header injection)."""
    return quote(str(value), safe=_HEADER_SAFE_CHARS)


# Integración que manda la acción como un POST con JSON a una URL
class HttpIntegration(Integration):
    """Sends the action as a JSON POST; non-null payload fields are also sent as headers."""

    def __init__(self, url: str, client: HttpClient, auth: Authenticator, method: str = "POST") -> None:
        self._url = url  # a dónde se envía
        self._client = client  # quién lo envía (el real o el de mentira)
        self._auth = auth  # cómo se autentica
        self._method = method  # POST por defecto

    # Montar la petición HTTP a partir de la acción (sin enviarla todavía)
    def build_request(self, action: Action, *, idempotency_key: str) -> HttpRequest:
        # PASO 1: la acción se convierte en su JSON
        payload = action.to_payload()
        # PASO 2: cada dato del JSON que no sea nulo también va como cabecera
        headers = {name: to_header_value(value) for name, value in payload.items() if value is not None}
        # PASO 3: añadir las cabeceras fijas. Van al final para que ningún dato
        # del payload pueda sobrescribirlas (p. ej. un campo llamado "Authorization").
        headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Idempotency-Key": idempotency_key,
                **self._auth.auth_headers(),
            }
        )
        # PASO 4: juntar todo en la petición
        return HttpRequest(method=self._method, url=self._url, headers=headers, json=payload)

    # Montar la petición, enviarla y traducir lo que pase a un ActionResult
    def execute(self, action: Action, *, idempotency_key: str) -> ActionResult:
        # PASO 1: montar la petición
        request = self.build_request(action, idempotency_key=idempotency_key)
        # PASO 2: enviarla. Si ni siquiera llega (red caída...) -> fallo
        try:
            response = self._client.send(request)
        except HttpTransportError as exc:
            logger.warning("Could not deliver %s to %s: %s", type(action).__name__, self._url, exc)
            return ActionResult(success=False, error=str(exc))
        # PASO 3: llegó, pero el servidor dijo que no (400, 500...) -> fallo
        if not response.ok:
            logger.warning("%s rejected %s with status %s", self._url, type(action).__name__, response.status_code)
            return ActionResult(success=False, status_code=response.status_code)
        # PASO 4: todo bien
        return ActionResult(success=True, status_code=response.status_code)
