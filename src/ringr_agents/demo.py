"""Run two scripted conversations and print the requests that would be sent.

RINGR_API_TOKEN=ringr_test_token_9f3a2c1d python -m ringr_agents.demo
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from ringr_agents.agents import BaseAgent
from ringr_agents.factory import AgentFactory, Settings
from ringr_agents.http_client import FakeHttpClient
from ringr_agents.models import ConversationModel, ParserModel


def _run(title: str, agent: BaseAgent, user_messages: list[str]) -> None:
    print(f"\n=== {title} ===")
    for message in user_messages:
        result = agent.handle_turn(message)
        print(f"usuario: {message}")
        print(f"agente:  {result.reply}")
        print(f"         datos={dict(result.parsed_data)} -> acción: {result.outcome.value}")


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    client = FakeHttpClient()
    factory = AgentFactory(Settings.from_env(), client)
    payment_day = (date.today() + timedelta(days=7)).isoformat()

    debt_agent = factory.debt_agent(
        ConversationModel(
            [
                "Hola, le llamo por la deuda pendiente de 300 €. ¿Cuándo podría pagarla?",
                "Perfecto. ¿Qué cantidad pagaría ese día?",
                "Queda registrado su compromiso. ¡Gracias!",
                "De nada, que tenga buen día.",
            ]
        ),
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

    assistance_agent = factory.assistance_agent(
        ConversationModel(["¿En qué puedo ayudarle?", "He registrado su solicitud, un agente le contactará."]),
        ParserModel([{"request": None}, {"request": "  Cambiar la dirección de facturación "}]),
    )
    _run("AssistanceAgent", assistance_agent, ["Hola", "Quiero cambiar la dirección de facturación"])

    print(f"\n=== Requests construidas ({len(client.sent_requests)}) ===")
    for request in client.sent_requests:
        print(f"{request.method} {request.url}")
        for name, value in request.headers.items():
            print(f"  {name}: {value}")
        print(f"  body: {json.dumps(dict(request.json), ensure_ascii=False)}")


if __name__ == "__main__":
    main()
