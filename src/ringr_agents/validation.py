"""Validation and normalization of the values returned by the ParserModel."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any


# Error que salta cuando la IA devuelve un dato con formato incorrecto
class InvalidFieldError(ValueError):
    """The parser returned a value that does not satisfy the field contract."""


# Comprobar que la fecha viene como texto 'aaaa-mm-dd' y convertirla en fecha de verdad
def parse_iso_date(value: Any) -> date:
    """Parse a strict 'yyyy-mm-dd' string."""
    # PASO 1: tiene que ser texto (no un número, ni una lista...)
    if not isinstance(value, str):
        raise InvalidFieldError(f"expected a 'yyyy-mm-dd' string, got {type(value).__name__}")
    # PASO 2: quitar espacios sobrantes e intentar leerla con el formato exacto
    try:
        # Se usa strptime y no date.fromisoformat porque desde Python 3.11 esta
        # última también acepta cosas como '20261105', que el contrato no permite.
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        # No encaja con el formato (p. ej. '2026-13-40') -> dato inválido
        raise InvalidFieldError(f"{value!r} is not a valid 'yyyy-mm-dd' date") from exc


# Comprobar que la cantidad es un número positivo y dejarla redondeada a céntimos
def parse_positive_amount(value: Any) -> float:
    """Parse a strictly positive, finite amount rounded to cents."""
    # PASO 1: tiene que ser un número. Ojo: True/False cuentan como números en
    # Python (True == 1), así que se descartan a mano.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidFieldError(f"expected a number, got {type(value).__name__}")
    amount = float(value)
    # PASO 2: nada de infinitos, NaN, cero ni negativos
    if not math.isfinite(amount) or amount <= 0:
        raise InvalidFieldError(f"{value!r} is not a positive finite amount")
    # PASO 3: redondear a 2 decimales (céntimos)
    return round(amount, 2)


# Limpiar un texto libre: quitar espacios y saltos de línea de más
def parse_text(value: Any) -> str | None:
    """Collapse whitespace (including newlines). Blank text counts as no value."""
    # PASO 1: tiene que ser texto
    if not isinstance(value, str):
        raise InvalidFieldError(f"expected a string, got {type(value).__name__}")
    # PASO 2: "  hola \n  mundo " -> "hola mundo"
    text = " ".join(value.split())
    # PASO 3: si se ha quedado vacío, es como si no hubiera dato -> None
    return text or None
