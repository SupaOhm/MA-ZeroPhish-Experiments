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
                 min_interval: float = 2.0, verify: bool = True, timeout: int = 300):
        provider, model = spec.split(":", 1)
        if provider not in PROVIDERS:
            raise SystemExit(f"unknown provider {provider!r}; use one of {sorted(PROVIDERS)}")
        load_env(env_path)
        base, key_name = PROVIDERS[provider]
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

    def chat(self, system: str, user: str, max_tokens: int = 2048, json_mode: bool = False) -> dict:
        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": user}]
        body = {"model": self.model, "temperature": 0, "max_completion_tokens": max_tokens,
                "messages": messages, **self.extra}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        sha = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
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
                low = text.lower()
                if any(w in low for w in ("per day", "tpd", "rpd", "daily", "quota")):
                    raise QuotaExhausted(text[:300])
                retry = float(headers.get("retry-after") or headers.get("Retry-After") or 0)
                time.sleep(max(retry, 2 ** attempt))
                continue
            if status >= 500:
                time.sleep(min(60, 2 ** attempt * 2))
                continue
            if status != 200:
                raise APIError(f"HTTP {status}: {text[:400]}")
            rec = {"request_sha": sha, "spec": self.spec, "model": self.model, "extra": self.extra,
                   "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "latency_s": latency,
                   "request": body, "response": json.loads(text)}
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
