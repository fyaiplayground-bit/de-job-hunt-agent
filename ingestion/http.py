"""Shared HTTP for all sources: honest identity, timeouts, and polite retries.

No disguise of any kind: every request says what it is and where its code lives. If a source
rate-limits us (429) or has a server error (5xx), we wait and retry a few times, then give up
and report the error instead of pushing harder.
"""

import time
from collections.abc import Callable
from typing import Any

import httpx

USER_AGENT = "de-job-hunt-agent/0.1 (+https://github.com/fyaiplayground-bit/de-job-hunt-agent)"
TIMEOUT_SECONDS = 30.0
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRIES = 3
MAX_WAIT_SECONDS = 60.0


class FetchError(RuntimeError):
    """A request failed for good (after retries, or with a status that isn't worth retrying)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """A client with our User-Agent and timeout. Tests pass a mock transport."""
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDS,
        transport=transport,
        follow_redirects=True,
    )


def _wait_seconds(response: httpx.Response | None, attempt: int) -> float:
    """Honor Retry-After when the server sends it in seconds; otherwise back off 1s, 2s, 4s."""
    if response is not None:
        retry_after = response.headers.get("Retry-After", "")
        if retry_after.strip().isdigit():
            return min(float(retry_after), MAX_WAIT_SECONDS)
    return min(2.0**attempt, MAX_WAIT_SECONDS)


def get_json(
    client: httpx.Client,
    url: str,
    params: dict[str, str] | None = None,
    *,
    retries: int = MAX_RETRIES,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """GET a URL and return the parsed JSON body, retrying only rate limits and server errors."""
    for attempt in range(retries + 1):
        last_try = attempt == retries
        try:
            response = client.get(url, params=params)
        except httpx.TransportError as exc:  # connection refused, timeout, DNS, ...
            if last_try:
                raise FetchError(f"GET {url} failed: {exc}") from exc
            sleep(_wait_seconds(None, attempt))
            continue

        if response.status_code in RETRY_STATUSES and not last_try:
            sleep(_wait_seconds(response, attempt))
            continue
        if response.status_code != 200:
            raise FetchError(
                f"GET {url} returned HTTP {response.status_code}", response.status_code
            )
        return response.json()

    raise AssertionError("unreachable")  # the loop always returns or raises
