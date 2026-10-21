"""Builds agents with their integrations."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from ringr_agents.agents import AssistanceAgent, DebtAgent
from ringr_agents.http_client import HttpClient
from ringr_agents.integrations import BearerTokenAuth, HttpIntegration
from ringr_agents.models import SupportsAnswerUser, SupportsParseData

TOKEN_ENV_VAR = "RINGR_API_TOKEN"


@dataclass(frozen=True)
class Settings:
    api_token: str = field(repr=False)
    debt_commitment_url: str = "https://api.ringr.debt/v1/commitment"
    assistance_request_url: str = "https://api.ringr.assistance/v1/request"

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        token = env.get(TOKEN_ENV_VAR)
        if not token:
            raise RuntimeError(f"Missing environment variable {TOKEN_ENV_VAR}")
        return cls(api_token=token)


class AgentFactory:
    def __init__(self, settings: Settings, http_client: HttpClient) -> None:
        self._settings = settings
        self._http_client = http_client
        self._auth = BearerTokenAuth(settings.api_token)

    def debt_agent(self, conversation_model: SupportsAnswerUser, parser_model: SupportsParseData) -> DebtAgent:
        integration = HttpIntegration(self._settings.debt_commitment_url, self._http_client, self._auth)
        return DebtAgent(conversation_model, parser_model, integration)

    def assistance_agent(
        self, conversation_model: SupportsAnswerUser, parser_model: SupportsParseData
    ) -> AssistanceAgent:
        integration = HttpIntegration(self._settings.assistance_request_url, self._http_client, self._auth)
        return AssistanceAgent(conversation_model, parser_model, integration)
