"""Runs one scripted conversation per agent and prints the requests built."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from ringr_agents.agents import BaseAgent
from ringr_agents.factory import AgentFactory, Settings
from ringr_agents.http_client import FakeHttpClient
from ringr_agents.models import ConversationModel, ParserModel


# Pasar al agente los mensajes del cliente uno a uno e imprimir qué ocurre en cada turno
def _run(title: str, agent: BaseAgent, user_messages: list[str]) -> None:
    print(f"\n=== {title} ===")
    for message in user_messages:
        result = agent.handle_turn(message)
        print(f"usuario: {message}")
        print(f"agente:  {result.reply}")
        print(f"         datos={dict(result.parsed_data)} -> acción: {result.outcome.value}")


def main() -> None:
    # PASO 1: preparar todo: logs, cliente HTTP de mentira y la fábrica de agentes
    logging.basicConfig(level=logging.WARNING)
    client = FakeHttpClient()
    factory = AgentFactory(Settings.from_env(), client)
    # Fecha de pago: dentro de una semana (así nunca está en el pasado)
    payment_day = (date.today() + timedelta(days=7)).isoformat()

    # PASO 2: conversación de deuda. Cada lista es el guion de una IA, un elemento por turno.
    debt_agent = factory.debt_agent(
        # Lo que contestará el agente en cada turno
        ConversationModel(
            [
                "Hola, le llamo por la deuda pendiente de 300 €. ¿Cuándo podría pagarla?",
                "Perfecto. ¿Qué cantidad pagaría ese día?",
                "Queda registrado su compromiso. ¡Gracias!",
                "De nada, que tenga buen día.",
            ]
        ),
        # La ficha que sacará la IA en cada turno: primero nada, luego fecha,
        # luego fecha + cantidad (se envía), y al final lo mismo (duplicado)
        ParserModel(
            [
                {"commitment_date": None, "committed_amount": None},
                {"commitment_date": payment_day, "committed_amount": None},
                {"commitment_date": payment_day, "committed_amount": 300},
                {"commitment_date": payment_day, "committed_amount": 300},
            ]
        ),
    )
    _run("DebtAgent", debt_agent, ["Hola", "La semana que viene", "Los 300 €", "Gracias"])

    # PASO 3: conversación de asistencia (el texto con espacios de más se limpia solo)
    assistance_agent = factory.assistance_agent(
        ConversationModel(["¿En qué puedo ayudarle?", "He registrado su solicitud, un agente le contactará."]),
        ParserModel([{"request": None}, {"request": "  Cambiar la dirección de facturación "}]),
    )
    _run("AssistanceAgent", assistance_agent, ["Hola", "Quiero cambiar la dirección de facturación"])

    # PASO 4: enseñar las peticiones HTTP que se habrían enviado de verdad
    print(f"\n=== Requests construidas ({len(client.sent_requests)}) ===")
    for request in client.sent_requests:
        print(f"{request.method} {request.url}")
        for name, value in request.headers.items():
            print(f"  {name}: {value}")
        print(f"  body: {json.dumps(dict(request.json), ensure_ascii=False)}")


# Solo se ejecuta si se lanza el archivo directamente (python -m ringr_agents.demo)
if __name__ == "__main__":
    main()
