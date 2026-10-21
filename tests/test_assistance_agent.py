import json

from ringr_agents.actions import AssistanceRequest
from ringr_agents.agents import ActionOutcome
from tests.constants import ASSISTANCE_URL


def test_no_action_without_request(make_assistance_agent, http_client):
    agent = make_assistance_agent([{"request": None}, {"request": "   "}, {}])

    outcomes = [agent.handle_turn("¿Qué horario tenéis?").outcome for _ in range(3)]

    assert outcomes == [ActionOutcome.NOT_REQUIRED] * 3
    assert http_client.sent_requests == []


def test_registers_normalized_request(make_assistance_agent, http_client):
    agent = make_assistance_agent([{"request": "  Cambiar\n la tarifa "}])

    result = agent.handle_turn("Quiero cambiar la tarifa")

    assert result.outcome == ActionOutcome.EXECUTED
    assert result.action == AssistanceRequest("Cambiar la tarifa")
    (request,) = http_client.sent_requests
    assert request.url == ASSISTANCE_URL
    assert request.headers["request"] == "Cambiar la tarifa"
    assert json.loads(request.body) == {"request": "Cambiar la tarifa"}


def test_same_request_is_not_sent_twice(make_assistance_agent, http_client):
    agent = make_assistance_agent([{"request": "Cambiar la tarifa"}, {"request": "Cambiar  la tarifa"}])

    agent.handle_turn("...")
    result = agent.handle_turn("...")

    assert result.outcome == ActionOutcome.DUPLICATE
    assert len(http_client.sent_requests) == 1


def test_different_request_in_same_conversation_is_registered(make_assistance_agent, http_client):
    agent = make_assistance_agent([{"request": "Cambiar la tarifa"}, {"request": "Dar de baja la línea 2"}])

    agent.handle_turn("...")
    result = agent.handle_turn("...")

    assert result.outcome == ActionOutcome.EXECUTED
    assert len(http_client.sent_requests) == 2


def test_invalid_request_type_is_ignored(make_assistance_agent, http_client):
    agent = make_assistance_agent([{"request": 42}])

    assert agent.handle_turn("...").outcome == ActionOutcome.NOT_REQUIRED
