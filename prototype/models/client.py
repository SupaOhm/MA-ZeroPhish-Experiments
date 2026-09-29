"""The model seam: one interface, two providers, and what a failed call is.

**A failed call is never an answer.** Transport errors, rate limits, server
errors and replies that are not a JSON object of the expected shape are retried
with backoff; when attempts run out the client raises `ModelCallFailed`, and the
case it belonged to is re-run rather than scored (data_eval HANDOFF §0 rule 5).

A reply that is well-formed but *wrong* -- a quote that is not in the evidence, a
citation that names no observation -- is not a failure of the call. It is the
model's answer, and the phases judge it: `validate` for specialists, Phase 4 Step
4 for the Judge.

Every attempt, failed or not, is written to the call log when one is attached.
"""

import hashlib
import json
import random
import time
from dataclasses import dataclass, field, replace


class ModelCallFailed(Exception):
    """Attempts exhausted, or a non-retryable error. Never a verdict."""

    def __init__(self, provider, reason, attempts, status=None, tag=None):
        super().__init__(f"{provider}: {reason} (after {attempts} attempt(s))")
        self.provider = provider
        self.reason = reason
        self.attempts = attempts
        self.status = status
        self.tag = dict(tag or {})


class Retryable(Exception):
    """Worth another attempt: transport, 408/429/5xx, unparseable or wrong shape.

    `raw` and the token counts are the provider's reply when there was one: a
    failed reply is still logged in full and its tokens are still spent.
    """

    def __init__(self, reason, status=None, retry_after=None, *, raw=None,
                 input_tokens=0, output_tokens=0):
        super().__init__(reason)
        self.reason = reason
        self.status = status
        self.retry_after = retry_after
        self.raw = raw
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class Fatal(Exception):
    """Not retried: another 4xx, a safety block, a truncated reply."""

    def __init__(self, reason, status=None, *, raw=None, input_tokens=0, output_tokens=0):
        super().__init__(reason)
        self.reason = reason
        self.status = status
        self.raw = raw
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _Unexpected:
    """How an unexpected exception is written to the call log."""

    def __init__(self, reason):
        self.reason = reason
        self.status = None


@dataclass(frozen=True, slots=True)
class ModelResponse:
    text: str
    parsed: dict | None
    input_tokens: int
    output_tokens: int
    latency_s: float
    model_version: str
    raw: dict = field(default_factory=dict)


@dataclass
class Usage:
    """Running totals for one client. `calls` counts `generate`, not attempts."""

    calls: int = 0
    attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def snapshot(self) -> tuple[int, int, int]:
        return (self.calls, self.input_tokens, self.output_tokens)


def parse_json_object(text: str) -> dict:
    """The reply as a JSON object. Tolerates one ```json fence, nothing else."""
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
        body = body.rstrip()
        if body.endswith("```"):
            body = body[:-3]
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        raise Retryable(f"invalid_json: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise Retryable("invalid_json: not an object")
    return value


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class BaseClient:
    provider = "base"

    def __init__(
        self,
        model: str,
        *,
        call_log=None,
        max_attempts: int = 4,
        min_interval_s: float = 0.0,
        backoff_s: float = 2.0,
        max_retry_after_s: float = 120.0,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        self.model = model
        self.call_log = call_log
        self.max_attempts = max_attempts
        self.min_interval_s = min_interval_s
        self.backoff_s = backoff_s
        self.max_retry_after_s = max_retry_after_s
        self.sleep = sleep
        self.clock = clock
        self.usage = Usage()
        self._last_start = None

    def _attempt(self, system, user, images, schema, tag) -> ModelResponse:
        raise NotImplementedError

    def generate(self, system, user, *, images=(), schema=None, validate=None, tag=None):
        tag = dict(tag or {})
        images = tuple(images)
        self.usage.calls += 1
        for attempt in range(1, self.max_attempts + 1):
            self._throttle()
            self.usage.attempts += 1
            started = self.clock()
            response, error = None, None
            try:
                response = self._attempt(system, user, images, schema, tag)
                response = replace(response, latency_s=round(self.clock() - started, 4))
                self.usage.input_tokens += response.input_tokens
                self.usage.output_tokens += response.output_tokens
                response = replace(response, parsed=parse_json_object(response.text))
                if validate is not None:
                    try:
                        validate(response.parsed)
                    except (ValueError, KeyError, TypeError) as exc:
                        raise Retryable(f"invalid_shape: {exc}") from exc
            except Retryable as exc:
                error = exc
                self._count_failed(response, exc)
            except Fatal as exc:
                self._count_failed(response, exc)
                self._log(system, user, images, tag, attempt, response, exc)
                raise ModelCallFailed(
                    self.provider, exc.reason, attempt, exc.status, tag
                ) from exc
            except Exception as exc:
                # A bug, not a provider failure: logged so no attempt goes
                # unrecorded, then raised to stop the run.
                self._log(system, user, images, tag, attempt, response,
                          _Unexpected(f"unexpected: {type(exc).__name__}: {exc}"))
                raise
            self._log(system, user, images, tag, attempt, response, error)
            if error is None:
                return response
            if attempt == self.max_attempts:
                raise ModelCallFailed(
                    self.provider, error.reason, attempt, error.status, tag
                ) from error
            self.sleep(self._delay(attempt, error))
        raise AssertionError("unreachable")

    def _count_failed(self, response, error) -> None:
        # A reply that parsed into a response was counted already; tokens a
        # provider reported on a reply it refused are counted here.
        if response is None:
            self.usage.input_tokens += getattr(error, "input_tokens", 0)
            self.usage.output_tokens += getattr(error, "output_tokens", 0)

    def _throttle(self):
        if self.min_interval_s > 0 and self._last_start is not None:
            wait = self.min_interval_s - (self.clock() - self._last_start)
            if wait > 0:
                self.sleep(wait)
        self._last_start = self.clock()

    def _delay(self, attempt: int, error: Retryable) -> float:
        # Capped: a provider asking for an hour stalls the run rather than
        # failing the case, and the cap bounds that stall.
        if error.retry_after is not None:
            delay = error.retry_after
        else:
            delay = self.backoff_s * 2 ** (attempt - 1) * (1 + 0.25 * random.random())
        return min(delay, self.max_retry_after_s)

    def _log(self, system, user, images, tag, attempt, response, error):
        if self.call_log is None:
            return
        self.call_log.write(
            {
                "provider": self.provider,
                "model": self.model,
                "model_version": response.model_version if response else None,
                "attempt": attempt,
                "ok": error is None,
                "error": getattr(error, "reason", None),
                "status": getattr(error, "status", None),
                "tag": tag,
                "system": system,
                "user": user,
                "image_sha256": [_sha256(image) for image in images],
                "text": response.text if response else None,
                "raw": response.raw if response else getattr(error, "raw", None),
                "input_tokens": (response.input_tokens if response
                                 else getattr(error, "input_tokens", 0)),
                "output_tokens": (response.output_tokens if response
                                  else getattr(error, "output_tokens", 0)),
                "latency_s": response.latency_s if response else None,
            }
        )
