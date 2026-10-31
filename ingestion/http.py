"""Shared HTTP for all sources: honest identity, timeouts, and polite retries.

No disguise (decision #25): the User-Agent uses the conventional crawler format, the same shape
as Googlebot's ("Mozilla/5.0 (compatible; name/version; +url)"), naming this project and where
its code lives; Accept / Accept-Language are ordinary content negotiation. We don't send headers
that imitate a site's own pages (such as X-Requested-With). If a source rate-limits us (429) or
has a server error (5xx), we wait and retry a few times, then give up and report the error
instead of pushing harder.
"""

import random
import time
from collections.abc import Callable
from typing import Any

import httpx

PROJECT_URL = "https://github.com/fyaiplayground-bit/de-job-hunt-agent"
USER_AGENT = f"Mozilla/5.0 (compatible; de-job-hunt-agent/0.1; +{PROJECT_URL})"
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT_SECONDS = 30.0
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRIES = 3
MAX_WAIT_SECONDS = 60.0
MAX_JITTER_SECONDS = 0.5  # random extra wait on backoff, so retries don't line up


class FetchError(RuntimeError):
    """A request failed for good (after retries, or with a status that isn't worth retrying)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """A client with our User-Agent and timeout. Tests pass a mock transport."""
    return httpx.Client(
        headers=DEFAULT_HEADERS,
        timeout=TIMEOUT_SECONDS,
        transport=transport,
        follow_redirects=True,
    )


def random_jitter() -> float:
    return random.uniform(0.0, MAX_JITTER_SECONDS)


def _wait_seconds(
    response: httpx.Response | None, attempt: int, jitter: Callable[[], float]
) -> float:
    """Honor Retry-After exactly when the server sends it in seconds; otherwise back off
    1s, 2s, 4s plus a little random jitter."""
    if response is not None:
        retry_after = response.headers.get("Retry-After", "")
        if retry_after.strip().isdigit():
            return min(float(retry_after), MAX_WAIT_SECONDS)
    return min(2.0**attempt + jitter(), MAX_WAIT_SECONDS)


Params = dict[str, str] | list[tuple[str, str]] | None  # a list allows repeated keys


def get_json(
    client: httpx.Client,
    url: str,
    params: Params = None,
    *,
    retries: int = MAX_RETRIES,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random_jitter,
) -> Any:
    """GET a URL and return the parsed JSON body, retrying only rate limits and server errors."""
    return _get(client, url, params, retries, sleep, jitter).json()


def get_text(
    client: httpx.Client,
    url: str,
    params: Params = None,
    *,
    retries: int = MAX_RETRIES,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random_jitter,
) -> str:
    """GET a URL and return the body as text (for sources that answer with HTML)."""
    return _get(client, url, params, retries, sleep, jitter).text


def _get(
    client: httpx.Client,
    url: str,
    params: Params,
    retries: int,
    sleep: Callable[[float], None],
    jitter: Callable[[], float],
) -> httpx.Response:
    for attempt in range(retries + 1):
        last_try = attempt == retries
        try:
            response = client.get(url, params=params)
        except httpx.TransportError as exc:  # connection refused, timeout, DNS, ...
            if last_try:
                raise FetchError(f"GET {url} failed: {exc}") from exc
            sleep(_wait_seconds(None, attempt, jitter))
            continue

        if response.status_code in RETRY_STATUSES and not last_try:
            sleep(_wait_seconds(response, attempt, jitter))
            continue
        if response.status_code != 200:
            raise FetchError(
                f"GET {url} returned HTTP {response.status_code}", response.status_code
            )
        return response

    raise AssertionError("unreachable")  # the loop always returns or raises
