"""Unit tests for ingestion/http.py using httpx's mock transport. No real network."""

import httpx
import pytest

from ingestion.http import USER_AGENT, FetchError, get_json, make_client


def client_returning(*responses: httpx.Response, seen: list | None = None) -> httpx.Client:
    """A client whose server answers with the given responses, one per request, in order."""
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return queue.pop(0)

    return make_client(transport=httpx.MockTransport(handler))


def test_returns_json_and_sends_our_user_agent():
    seen = []
    client = client_returning(httpx.Response(200, json={"jobs": []}), seen=seen)

    assert get_json(client, "https://api.example/jobs") == {"jobs": []}
    assert seen[0].headers["User-Agent"] == USER_AGENT


def test_rate_limit_waits_for_retry_after_then_succeeds():
    waits = []
    client = client_returning(
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(200, json=[1, 2]),
    )

    assert get_json(client, "https://api.example/jobs", sleep=waits.append) == [1, 2]
    assert waits == [7.0]


def test_server_errors_back_off_then_give_up():
    waits = []
    client = client_returning(*[httpx.Response(503) for _ in range(4)])

    with pytest.raises(FetchError, match="HTTP 503") as error:
        get_json(client, "https://api.example/jobs", sleep=waits.append)

    assert waits == [1.0, 2.0, 4.0]  # 3 retries, then stop
    assert error.value.status_code == 503


def test_not_found_is_not_retried():
    waits = []
    client = client_returning(httpx.Response(404))

    with pytest.raises(FetchError, match="HTTP 404"):
        get_json(client, "https://api.example/missing-board", sleep=waits.append)

    assert waits == []


def test_connection_errors_are_retried_then_reported():
    waits = []

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = make_client(transport=httpx.MockTransport(handler))

    with pytest.raises(FetchError, match="connection refused"):
        get_json(client, "https://api.example/jobs", sleep=waits.append)

    assert len(waits) == 3
