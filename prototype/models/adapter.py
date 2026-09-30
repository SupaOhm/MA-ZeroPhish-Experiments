"""Shared model adapter: one client for every arm that calls a real LLM.

Standard library only, like the rest of the prototype. OpenAI-compatible chat
endpoints of the free providers the team screened (Groq, Gemini API, NVIDIA NIM,
OpenRouter).

Rules this module enforces (paper Sec. IV + team rules):
* **Real calls only.** There is no fallback model and no simulated answer. A missing
  key or an unknown model id aborts the run.
* **Every call is logged raw** (prompt, raw response, usage, latency, timestamp,
  model, request hash) to `<cache_dir>/<request_sha>.json`. The same request is
  served from that file on re-runs, so an interrupted run resumes without paying
  twice and every number stays traceable to a stored response.
* **API failures are never answers.** 429/5xx/network errors are retried with
  backoff; a daily-quota 429 raises `QuotaExhausted`; any other non-200 raises
  `APIError`. Callers must not turn either into a verdict.

    from models.adapter import ChatModel
    m = ChatModel("groq:openai/gpt-oss-120b", env_path="../.env", cache_dir="runs/cache",
                  extra={"reasoning_effort": "low"})
    out = m.chat(system, user, max_tokens=2048)
    out["text"], out["input_tokens"], out["output_tokens"], out["latency_s"], out["request_sha"]
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "nvidia": ("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    # Paid. Pin a dated snapshot (e.g. gpt-4o-mini-2024-07-18) so the version is fixed.
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
}
_UA = "MA-ZeroPhish-research/1.0"


class APIError(Exception):
    """The provider refused the request (not a model answer)."""


class QuotaExhausted(Exception):
    """Daily quota reached; re-run later, the cache resumes the work."""


def load_env(path: str | os.PathLike | None) -> None:
    if not path or not Path(path).exists():
        return
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and v and k not in os.environ:
                os.environ[k] = v


def classify_429(text: str, headers: dict) -> tuple[bool, float]:
    """(is_daily_quota, seconds_to_wait) for a 429 body.

    Providers say "quota" for per-minute limits too (Gemini: "You exceeded your
    current quota" with quotaId ...PerMinute...), so only an explicit per-day marker
    counts as the daily cap; everything else is waited out.
    """
    low = text.lower()
    daily = any(w in low for w in ("perday", "per day", "per_day", "daily", "requests per day",
                                   "tokens per day", "(rpd)", "(tpd)", " rpd", " tpd"))
    wait = float(headers.get("retry-after") or headers.get("Retry-After") or 0)
    try:
        body = json.loads(text)
        body = body[0] if isinstance(body, list) else body
        for det in (body.get("error") or {}).get("details", []):
            for v in det.get("violations", []) or []:
                qid = str(v.get("quotaId", "")).lower()
                if "perday" in qid:
                    daily = True
                elif "perminute" in qid:
                    daily = daily and False
            if "retryDelay" in det:
                wait = max(wait, float(str(det["retryDelay"]).rstrip("s") or 0))
    except (ValueError, AttributeError, TypeError):
        pass
    return daily, wait


def _http(method: str, url: str, headers: dict, body: dict | None, timeout: int):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={**headers, "User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read().decode("utf-8", "replace")


class ChatModel:
    def __init__(self, spec: str, env_path=None, cache_dir="runs/cache", extra: dict | None = None,
                 min_interval: float = 2.0, verify: bool = True, timeout: int = 300,
                 key_env: str | None = None):
        """`key_env` names a different environment variable for the key (e.g. a
        teammate's own key for their share of the work); the NAME is recorded, never
        the key."""
        provider, model = spec.split(":", 1)
        if provider not in PROVIDERS:
            raise SystemExit(f"unknown provider {provider!r}; use one of {sorted(PROVIDERS)}")
        load_env(env_path)
        base, key_name = PROVIDERS[provider]
        key_name = key_env or key_name
        self.key_env = key_name
        key = os.environ.get(key_name, "")
        if not key:
            raise SystemExit(f"{key_name} is not set. Refusing to run: no simulated fallback exists.")
        self.spec, self.provider, self.model, self.base = spec, provider, model, base
        self.extra = dict(extra or {})
        self.cache = Path(cache_dir) / spec.replace("/", "_").replace(":", "_")
        self.cache.mkdir(parents=True, exist_ok=True)
        self._headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        self._timeout, self._min_interval = timeout, min_interval
        self._lock, self._next = threading.Lock(), 0.0
        self.n_429 = 0
        if verify:
            self._verify()

    def _verify(self) -> None:
        status, _, text = _http("GET", f"{self.base}/models", self._headers, None, 60)
        if status == 401:
            raise SystemExit("API key rejected (401).")
        if status != 200:
            raise SystemExit(f"model listing failed: HTTP {status} {text[:200]}")
        ids = {m.get("id", "").removeprefix("models/") for m in json.loads(text).get("data", [])}
        if self.model not in ids:
            raise SystemExit(f"model {self.model!r} not offered by {self.provider}")

    def _turn(self) -> None:
        with self._lock:
            now = time.time()
            start = max(now, self._next)
            self._next = start + self._min_interval
        if start > now:
            time.sleep(start - now)

    def chat(self, system: str, user: str, max_tokens: int = 2048, json_mode: bool = False,
             images: list | None = None) -> dict:
        """`images`: PNG file paths sent with the user turn as OpenAI `image_url` parts
        (detail "low"). The cache key and the stored request hold each image's SHA-256
        instead of its bytes. Without images the request (and its cache key) is unchanged."""
        parts, keyparts = [], []
        for img in images or []:
            data = Path(img).read_bytes()
            parts.append({"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(data).decode(), "detail": "low"}})
            keyparts.append({"type": "image_url", "image_url": {
                "url": "sha256:" + hashlib.sha256(data).hexdigest(), "detail": "low"}})

        def build(img_parts: list) -> dict:
            content = ([{"type": "text", "text": user}] + img_parts) if img_parts else user
            messages = ([{"role": "system", "content": system}] if system else []) + \
                       [{"role": "user", "content": content}]
            b = {"model": self.model, "temperature": 0, "max_completion_tokens": max_tokens,
                 "messages": messages, **self.extra}
            if json_mode:
                b["response_format"] = {"type": "json_object"}
            return b
        body, key_body = build(parts), build(keyparts)
        sha = hashlib.sha256(json.dumps(key_body, sort_keys=True).encode()).hexdigest()
        path = self.cache / f"{sha}.json"
        if path.exists():
            rec = json.loads(path.read_text(encoding="utf-8"))
            return self._result(rec, cached=True)
        for attempt in range(8):
            self._turn()
            t0 = time.time()
            try:
                status, headers, text = _http("POST", f"{self.base}/chat/completions",
                                              self._headers, body, self._timeout)
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                time.sleep(min(60, 5 * 2 ** attempt))
                continue
            latency = time.time() - t0
            if status == 429:
                self.n_429 += 1
                daily, wait = classify_429(text, headers)
                if daily:
                    raise QuotaExhausted(text[:300])
                time.sleep(min(120, max(wait, 5 * 2 ** attempt)))
                continue
            if status >= 500:
                time.sleep(min(60, 2 ** attempt * 2))
                continue
            if status == 402:
                # OpenRouter: credits exhausted / spend limit reached. Stop the run (resumable),
                # exactly like a daily quota -- never fail case after case.
                raise QuotaExhausted(f"HTTP 402 (credits/spend limit): {text[:300]}")
            if status != 200:
                raise APIError(f"HTTP {status}: {text[:400]}")
            try:
                payload = json.loads(text)
            except ValueError:
                raise APIError(f"HTTP 200 with non-JSON body: {text[:200]}")
            if payload.get("error") or not payload.get("choices"):
                # A 200 carrying an error / no choices is a transport failure, not an answer:
                # never cached, never scored.
                raise APIError(f"HTTP 200 without an answer: {str(payload.get('error') or text)[:300]}")
            rec = {"request_sha": sha, "spec": self.spec, "model": self.model, "extra": self.extra,
                   "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "latency_s": latency,
                   "request": key_body, "response": payload}
            path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
            return self._result(rec, cached=False)
        raise APIError("gave up after repeated 429/5xx/network errors")

    @staticmethod
    def _result(rec: dict, cached: bool) -> dict:
        resp = rec["response"]
        choice = (resp.get("choices") or [{}])[0]
        usage = resp.get("usage") or {}
        return {"text": (choice.get("message") or {}).get("content") or "",
                "finish_reason": choice.get("finish_reason"),
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "latency_s": rec.get("latency_s", 0.0), "request_sha": rec["request_sha"],
                "model": rec["model"], "cached": cached}
