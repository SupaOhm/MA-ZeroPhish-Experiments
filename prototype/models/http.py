"""One POST, and what its status means for retrying. Standard library only."""

import http.client
import json
import urllib.error
import urllib.request

from .client import Fatal, Retryable

RETRY_STATUSES = frozenset({408, 429})


def http_post(url: str, headers: dict, body: bytes, timeout_s: float):
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as exc:
        raise Retryable(f"transport: {exc}") from exc


def check_status(status: int, headers: dict, body: bytes) -> dict:
    """The decoded JSON body of a 200; otherwise the right exception."""
    text = body.decode("utf-8", errors="replace")
    if status == 200:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise Retryable(f"invalid_envelope: {exc.msg}", status) from exc
    reason = f"http_{status}: {text[:300]}"
    if status in RETRY_STATUSES or status >= 500:
        lowered = {str(k).lower(): v for k, v in headers.items()}
        retry_after = None
        try:
            retry_after = float(lowered["retry-after"])
        except (KeyError, ValueError):
            if status == 429:
                retry_after = _retry_delay(text)
        raise Retryable(reason, status, retry_after)
    raise Fatal(reason, status)


def _retry_delay(text: str) -> float | None:
    """Gemini's 429 body names the wait: error.details[].retryDelay, e.g. "30s"."""
    try:
        details = json.loads(text)["error"]["details"]
        for detail in details:
            if str(detail.get("@type", "")).endswith("RetryInfo"):
                delay = str(detail["retryDelay"])
                return float(delay[:-1] if delay.endswith("s") else delay)
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    return None
