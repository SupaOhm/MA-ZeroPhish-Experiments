"""OpenRouter client (OpenAI-compatible chat completions). Key from `OPENROUTER_API_KEY`.

Not every routed model supports `response_format: json_schema`; pass
`structured=False` for those and rely on the prompt plus the local shape check.
"""

import base64
import json
import os

from .client import BaseClient, Fatal, ModelResponse, Retryable
from .http import check_status, http_post

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterClient(BaseClient):
    provider = "openrouter"

    def __init__(
        self, model, *, api_key=None, structured=True, system_role=True,
        temperature=0.0, timeout_s=300.0, transport=http_post, **kw,
    ):
        super().__init__(model, **kw)
        self._key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY", "")
        if not self._key:
            raise ValueError("OPENROUTER_API_KEY is not set")
        self.structured = structured
        self.system_role = system_role
        self.temperature = temperature
        self.timeout_s = timeout_s
        self.transport = transport

    def build_request(self, system, user, images, schema):
        content = [{"type": "text", "text": user}]
        for png in images:
            data = base64.b64encode(png).decode("ascii")
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}
            )
        messages = []
        if self.system_role:
            messages.append({"role": "system", "content": system})
        else:
            content.insert(0, {"type": "text", "text": system})
        messages.append({"role": "user", "content": content})
        body = {"model": self.model, "messages": messages, "temperature": self.temperature}
        if self.structured and schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "strict": True, "schema": schema},
            }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._key}",
            "X-Title": "MA-ZeroPhish experiments",
        }
        return ENDPOINT, headers, body

    def parse_response(self, payload: dict) -> ModelResponse:
        if "error" in payload:
            error = payload["error"] or {}
            code = error.get("code")
            reason = f"provider_error_{code}: {str(error.get('message', ''))[:300]}"
            if code in (408, 429) or (isinstance(code, int) and code >= 500):
                raise Retryable(reason, code if isinstance(code, int) else None)
            raise Fatal(reason, code if isinstance(code, int) else None)
        choices = payload.get("choices") or []
        if not choices:
            raise Retryable("no_choices")
        choice = choices[0]
        finish = choice.get("finish_reason") or ""
        if finish == "length":
            raise Fatal("truncated: length")
        if finish == "content_filter":
            raise Fatal("blocked: content_filter")
        content = (choice.get("message") or {}).get("content") or ""
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        usage = payload.get("usage") or {}
        return ModelResponse(
            text=content,
            parsed=None,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            latency_s=0.0,
            model_version=payload.get("model", self.model),
            raw=payload,
        )

    def _attempt(self, system, user, images, schema, tag):
        url, headers, body = self.build_request(system, user, images, schema)
        status, response_headers, raw = self.transport(
            url, headers, json.dumps(body).encode("utf-8"), self.timeout_s
        )
        return self.parse_response(check_status(status, response_headers, raw))
