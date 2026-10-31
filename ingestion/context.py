"""What a source's fetch_jobs() gets: the HTTP client, the target's options, and a request budget.

Every request a source makes goes through `ctx.get_json()` / `ctx.get_text()`, so the context
can count them and enforce a hard cap (LinkedIn: a per-day maximum, decision #24). When the
cap is reached the next request raises BudgetExhausted; the source stops and returns what it has.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from ingestion import http


class BudgetExhausted(RuntimeError):
    """The request budget for this run is used up."""


@dataclass
class FetchContext:
    client: httpx.Client
    options: dict[str, Any] = field(default_factory=dict)  # from config/searches.toml
    request_budget: int | None = None  # max requests this run may make; None = no cap
    known_job_ids: frozenset[str] = frozenset()  # jobs already stored for this source
    sleep: Callable[[float], None] = time.sleep
    requests_made: int = 0
    budget_exhausted: bool = False
    # Jobs seen on the source but not fetched again because they're already stored:
    # (company, source job id), so the load can still record that they were seen today.
    seen_only: list[tuple[str, str]] = field(default_factory=list)

    def _spend(self) -> None:
        if self.request_budget is not None and self.requests_made >= self.request_budget:
            self.budget_exhausted = True
            raise BudgetExhausted(f"request budget of {self.request_budget} used up")
        self.requests_made += 1

    def get_json(self, url: str, params: http.Params = None) -> Any:
        self._spend()
        return http.get_json(self.client, url, params, sleep=self.sleep)

    def get_text(self, url: str, params: http.Params = None) -> str:
        self._spend()
        return http.get_text(self.client, url, params, sleep=self.sleep)
