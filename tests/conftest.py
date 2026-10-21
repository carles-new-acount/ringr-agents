import pytest

from ringr_agents.agents import AssistanceAgent, DebtAgent
from ringr_agents.http_client import FakeHttpClient
from ringr_agents.integrations import BearerTokenAuth, HttpIntegration
from ringr_agents.models import ConversationModel, ParserModel
from tests.constants import ASSISTANCE_URL, DEBT_URL, TEST_TOKEN, TODAY


@pytest.fixture
def http_client() -> FakeHttpClient:
    return FakeHttpClient()


@pytest.fixture
def make_debt_agent(http_client):
    """Builds a DebtAgent whose parser returns `parsed_turns`, one per turn."""

    def _make(parsed_turns: list[dict]) -> DebtAgent:
        integration = HttpIntegration(DEBT_URL, http_client, BearerTokenAuth(TEST_TOKEN))
        return DebtAgent(
            ConversationModel([f"respuesta {i}" for i in range(len(parsed_turns))]),
            ParserModel(parsed_turns),
            integration,
            today=lambda: TODAY,
        )

    return _make


@pytest.fixture
def make_assistance_agent(http_client):
    def _make(parsed_turns: list[dict]) -> AssistanceAgent:
        integration = HttpIntegration(ASSISTANCE_URL, http_client, BearerTokenAuth(TEST_TOKEN))
        return AssistanceAgent(
            ConversationModel([f"respuesta {i}" for i in range(len(parsed_turns))]),
            ParserModel(parsed_turns),
            integration,
        )

    return _make
