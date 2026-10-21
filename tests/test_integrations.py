import json
from datetime import date

import pytest

from ringr_agents.actions import AssistanceRequest, PaymentCommitment, idempotency_key
from ringr_agents.http_client import FakeHttpClient, HttpTransportError
from ringr_agents.integrations import BearerTokenAuth, HttpIntegration, to_header_value
from tests.constants import ASSISTANCE_URL, DEBT_URL, TEST_TOKEN

COMMITMENT = PaymentCommitment(date(2026, 11, 5), 150.5)


def _integration(client: FakeHttpClient, url: str = DEBT_URL) -> HttpIntegration:
    return HttpIntegration(url, client, BearerTokenAuth(TEST_TOKEN))


class TestBuildRequest:
    def test_builds_post_to_endpoint_with_json_body(self):
        request = _integration(FakeHttpClient()).build_request(COMMITMENT, idempotency_key="k")

        assert request.method == "POST"
        assert request.url == DEBT_URL
        assert json.loads(request.body) == {"commitment_date": "2026-11-05", "committed_amount": 150.5}

    def test_includes_auth_content_type_and_idempotency_headers(self):
        request = _integration(FakeHttpClient()).build_request(COMMITMENT, idempotency_key="k")

        assert request.headers["Authorization"] == f"Bearer {TEST_TOKEN}"
        assert request.headers["Content-Type"] == "application/json"
        assert request.headers["Idempotency-Key"] == "k"

    def test_parsed_data_is_sent_as_headers_with_same_names(self):
        request = _integration(FakeHttpClient()).build_request(COMMITMENT, idempotency_key="k")

        assert request.headers["commitment_date"] == "2026-11-05"
        assert request.headers["committed_amount"] == "150.5"

    def test_non_ascii_header_values_are_percent_encoded_but_body_keeps_original(self):
        action = AssistanceRequest("Cambiar dirección")
        request = _integration(FakeHttpClient(), ASSISTANCE_URL).build_request(action, idempotency_key="k")

        assert request.headers["request"] == "Cambiar direcci%C3%B3n"
        assert request.json["request"] == "Cambiar dirección"

    def test_request_is_immutable(self):
        request = _integration(FakeHttpClient()).build_request(COMMITMENT, idempotency_key="k")

        with pytest.raises(TypeError):
            request.headers["Authorization"] = "Bearer otro"


class TestHeaderValue:
    def test_cr_lf_cannot_inject_new_headers(self):
        assert "\r" not in to_header_value("x\r\nX-Admin: true")
        assert "\n" not in to_header_value("x\r\nX-Admin: true")

    def test_percent_sign_is_escaped_so_encoding_is_reversible(self):
        assert to_header_value("100%") == "100%25"


class TestExecute:
    def test_success_records_request(self):
        client = FakeHttpClient()

        result = _integration(client).execute(COMMITMENT, idempotency_key="k")

        assert result.success
        assert result.status_code == 200
        assert len(client.sent_requests) == 1

    def test_non_2xx_is_reported_as_failure(self):
        result = _integration(FakeHttpClient(status_code=503)).execute(COMMITMENT, idempotency_key="k")

        assert not result.success
        assert result.status_code == 503

    def test_transport_error_is_reported_as_failure_without_raising(self):
        client = FakeHttpClient(error=HttpTransportError("timeout"))

        result = _integration(client).execute(COMMITMENT, idempotency_key="k")

        assert not result.success
        assert result.error == "timeout"


class TestSecrets:
    def test_token_is_not_in_repr(self):
        assert TEST_TOKEN not in repr(BearerTokenAuth(TEST_TOKEN))


class TestIdempotencyKey:
    def test_same_conversation_and_action_give_same_key(self):
        assert idempotency_key("c1", COMMITMENT) == idempotency_key("c1", PaymentCommitment(date(2026, 11, 5), 150.5))

    def test_different_conversation_or_data_give_different_key(self):
        other = PaymentCommitment(date(2026, 11, 5), 200.0)
        assert idempotency_key("c1", COMMITMENT) != idempotency_key("c2", COMMITMENT)
        assert idempotency_key("c1", COMMITMENT) != idempotency_key("c1", other)
