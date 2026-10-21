import json
from datetime import date

from ringr_agents.actions import PaymentCommitment
from ringr_agents.agents import ActionOutcome
from ringr_agents.conversation import Role
from tests.constants import DEBT_URL

EMPTY = {"commitment_date": None, "committed_amount": None}
FULL = {"commitment_date": "2026-11-05", "committed_amount": 150}


def test_turn_returns_model_reply_and_records_both_messages(make_debt_agent):
    agent = make_debt_agent([EMPTY])

    result = agent.handle_turn("Hola")

    assert result.reply == "respuesta 0"
    assert [m.role for m in agent.conversation.messages] == [Role.USER, Role.AGENT]


def test_no_action_until_both_fields_are_present(make_debt_agent, http_client):
    agent = make_debt_agent(
        [
            EMPTY,
            {"commitment_date": "2026-11-05", "committed_amount": None},
            {"commitment_date": None, "committed_amount": 150},
        ]
    )

    outcomes = [agent.handle_turn("...").outcome for _ in range(3)]

    assert outcomes == [ActionOutcome.NOT_REQUIRED] * 3
    assert http_client.sent_requests == []


def test_registers_commitment_when_both_fields_are_present(make_debt_agent, http_client):
    agent = make_debt_agent([FULL])

    result = agent.handle_turn("El 5 de noviembre pago 150")

    assert result.outcome == ActionOutcome.EXECUTED
    assert result.action == PaymentCommitment(date(2026, 11, 5), 150.0)
    (request,) = http_client.sent_requests
    assert request.url == DEBT_URL
    assert json.loads(request.body) == {"commitment_date": "2026-11-05", "committed_amount": 150.0}


def test_same_commitment_is_not_sent_twice(make_debt_agent, http_client):
    agent = make_debt_agent([FULL, FULL, FULL])

    outcomes = [agent.handle_turn("...").outcome for _ in range(3)]

    assert outcomes == [ActionOutcome.EXECUTED, ActionOutcome.DUPLICATE, ActionOutcome.DUPLICATE]
    assert len(http_client.sent_requests) == 1


def test_equivalent_values_after_normalization_are_duplicates(make_debt_agent, http_client):
    agent = make_debt_agent([FULL, {"commitment_date": " 2026-11-05", "committed_amount": 150.0}])

    agent.handle_turn("...")
    result = agent.handle_turn("...")

    assert result.outcome == ActionOutcome.DUPLICATE
    assert len(http_client.sent_requests) == 1


def test_changed_commitment_is_registered_again(make_debt_agent, http_client):
    agent = make_debt_agent([FULL, {"commitment_date": "2026-11-05", "committed_amount": 200}])

    agent.handle_turn("...")
    result = agent.handle_turn("Mejor 200")

    assert result.outcome == ActionOutcome.EXECUTED
    assert len(http_client.sent_requests) == 2


def test_invalid_values_never_trigger_an_action(make_debt_agent, http_client):
    agent = make_debt_agent(
        [
            {"commitment_date": "05/11/2026", "committed_amount": 150},
            {"commitment_date": "2026-11-05", "committed_amount": -150},
            {"commitment_date": "2026-11-05", "committed_amount": "150"},
        ]
    )

    outcomes = [agent.handle_turn("...").outcome for _ in range(3)]

    assert outcomes == [ActionOutcome.NOT_REQUIRED] * 3
    assert http_client.sent_requests == []


def test_past_date_is_rejected(make_debt_agent, http_client):
    agent = make_debt_agent([{"commitment_date": "2026-10-20", "committed_amount": 150}])

    assert agent.handle_turn("Pagué ayer").outcome == ActionOutcome.NOT_REQUIRED


def test_today_is_a_valid_commitment_date(make_debt_agent):
    agent = make_debt_agent([{"commitment_date": "2026-10-21", "committed_amount": 150}])

    assert agent.handle_turn("Hoy").outcome == ActionOutcome.EXECUTED


def test_missing_keys_are_treated_as_null(make_debt_agent):
    agent = make_debt_agent([{}])

    assert agent.handle_turn("...").outcome == ActionOutcome.NOT_REQUIRED


def test_failed_action_is_retried_on_next_turn(make_debt_agent, http_client):
    agent = make_debt_agent([FULL, FULL])
    http_client.status_code = 500

    first = agent.handle_turn("...")
    http_client.status_code = 200
    second = agent.handle_turn("...")

    assert first.outcome == ActionOutcome.FAILED
    assert first.reply == "respuesta 0"  # the user still gets an answer
    assert second.outcome == ActionOutcome.EXECUTED


def test_retry_after_failure_reuses_idempotency_key(make_debt_agent, http_client):
    agent = make_debt_agent([FULL, FULL])
    http_client.status_code = 500
    agent.handle_turn("...")
    http_client.status_code = 200
    agent.handle_turn("...")

    first, retry = http_client.sent_requests
    assert first.headers["Idempotency-Key"] == retry.headers["Idempotency-Key"]
