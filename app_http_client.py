"""Small shared HTTP client for ESI/zKill/image requests.

Runtime modules should use this instead of creating ad-hoc requests calls.
It gives the app one User-Agent, one requests.Session, consistent timeouts,
and basic retry/backoff for temporary HTTP failures.
"""

from __future__ import annotations

import time
from typing import Any, Iterable

import requests

DEFAULT_USER_AGENT = "EVE-Local-Intel-Scanner/2.0.0 (+https://github.com/devCote/eve-local-scaner)"
DEFAULT_TIMEOUT = 8
RETRY_STATUS_CODES = {420, 429, 500, 502, 503, 504}

_SESSION = requests.Session()


def _headers(user_agent: str | None = None, accept_json: bool = True) -> dict[str, str]:
    headers = {
        "User-Agent": user_agent or DEFAULT_USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
    }
    if accept_json:
        headers["Accept"] = "application/json"
    return headers


def request(
    method: str,
    url: str,
    *,
    user_agent: str | None = None,
    timeout: int | float = DEFAULT_TIMEOUT,
    retries: int = 1,
    accept_json: bool = True,
    **kwargs: Any,
) -> requests.Response:
    headers = dict(_headers(user_agent=user_agent, accept_json=accept_json))
    extra_headers = kwargs.pop("headers", None)
    if isinstance(extra_headers, dict):
        headers.update(extra_headers)

    last_error: Exception | None = None
    for attempt in range(max(0, int(retries)) + 1):
        try:
            response = _SESSION.request(
                method.upper(),
                url,
                headers=headers,
                timeout=timeout,
                **kwargs,
            )
            # ESI publishes an error-limit budget. If we are near the floor,
            # pause briefly before returning so future calls do not immediately
            # trip the limit. This is intentionally conservative and tiny.
            try:
                remain = int(response.headers.get("X-ESI-Error-Limit-Remain", "100"))
                reset = int(response.headers.get("X-ESI-Error-Limit-Reset", "0"))
                if remain <= 5 and reset > 0:
                    time.sleep(min(max(reset, 1), 5))
            except Exception:
                pass

            if response.status_code not in RETRY_STATUS_CODES or attempt >= retries:
                return response
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                raise

        time.sleep(0.35 * (attempt + 1))

    if last_error:
        raise last_error
    raise RuntimeError(f"HTTP request failed: {method} {url}")


def get_json(
    url: str,
    *,
    user_agent: str | None = None,
    timeout: int | float = DEFAULT_TIMEOUT,
    retries: int = 1,
    allowed_status: Iterable[int] = (200,),
) -> Any | None:
    response = request(
        "GET",
        url,
        user_agent=user_agent,
        timeout=timeout,
        retries=retries,
        accept_json=True,
    )
    if response.status_code not in set(allowed_status):
        return None
    return response.json()


def post_json(
    url: str,
    payload: Any,
    *,
    user_agent: str | None = None,
    timeout: int | float = DEFAULT_TIMEOUT,
    retries: int = 1,
    allowed_status: Iterable[int] = (200,),
) -> Any | None:
    response = request(
        "POST",
        url,
        json=payload,
        user_agent=user_agent,
        timeout=timeout,
        retries=retries,
        accept_json=True,
    )
    if response.status_code not in set(allowed_status):
        return None
    return response.json()


def get_bytes(
    url: str,
    *,
    user_agent: str | None = None,
    timeout: int | float = DEFAULT_TIMEOUT,
    retries: int = 1,
) -> bytes:
    response = request(
        "GET",
        url,
        user_agent=user_agent,
        timeout=timeout,
        retries=retries,
        accept_json=False,
    )
    response.raise_for_status()
    return response.content or b""
