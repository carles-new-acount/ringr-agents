import pytest

from ringr_agents.agents import ActionOutcome, AssistanceAgent, DebtAgent
from ringr_agents.factory import AgentFactory, Settings
from ringr_agents.models import ConversationModel, ParserModel
from tests.constants import ASSISTANCE_URL, DEBT_URL, TEST_TOKEN


def test_settings_read_token_from_env():
    assert Settings.from_env({"RINGR_API_TOKEN": TEST_TOKEN}).api_token == TEST_TOKEN


def test_settings_fail_fast_without_token():
    with pytest.raises(RuntimeError, match="RINGR_API_TOKEN"):
        Settings.from_env({})


def test_settings_repr_hides_token():
    assert TEST_TOKEN not in repr(Settings(api_token=TEST_TOKEN))


def test_factory_wires_each_agent_to_its_endpoint(http_client):
    factory = AgentFactory(Settings(api_token=TEST_TOKEN), http_client)

    debt = factory.debt_agent(
        ConversationModel(["ok"]), ParserModel([{"commitment_date": "2999-01-01", "committed_amount": 10}])
    )
    assistance = factory.assistance_agent(ConversationModel(["ok"]), ParserModel([{"request": "Llamadme"}]))

    assert isinstance(debt, DebtAgent)
    assert isinstance(assistance, AssistanceAgent)
    assert debt.handle_turn("...").outcome == ActionOutcome.EXECUTED
    assert assistance.handle_turn("...").outcome == ActionOutcome.EXECUTED
    assert [r.url for r in http_client.sent_requests] == [DEBT_URL, ASSISTANCE_URL]
    assert all(r.headers["Authorization"] == f"Bearer {TEST_TOKEN}" for r in http_client.sent_requests)
