"""Gemini API client (`generateContent`, v1beta). Key from `GEMINI_API_KEY`.

Structured output uses `responseSchema`, which accepts an OpenAPI-style subset
of JSON Schema, so `to_gemini_schema` converts ours. Some models served here
(Gemma) may not accept a system instruction or JSON mode: `system_role=False`
and `structured=False` fall back to plain prompting, and the local shape check
still applies. Confirm the right flags per model in the first smoke run.
"""

import base64
import json
import os

from .client import BaseClient, Fatal, ModelResponse
from .http import check_status, http_post

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
BLOCKING_FINISH = frozenset(
    {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}
)
_KEPT_KEYS = ("enum", "required", "description", "minimum", "maximum")
# The evidence is phishing content, which trips these filters. Category and
# threshold names follow the v1beta docs; confirm them in the first smoke run
# (a rejected name is an http_400, a blocked reply a `blocked:` failure).
SAFETY_CATEGORIES = (
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
)


def to_gemini_schema(schema: dict) -> dict:
    converted = {}
    for key, value in schema.items():
        if key == "type":
            converted["type"] = value.upper()
        elif key == "properties":
            converted["properties"] = {k: to_gemini_schema(v) for k, v in value.items()}
        elif key == "items":
            converted["items"] = to_gemini_schema(value)
        elif key in _KEPT_KEYS:
            converted[key] = value
    return converted


class GeminiClient(BaseClient):
    provider = "gemini"

    def __init__(
        self, model, *, api_key=None, structured=True, system_role=True,
        temperature=0.0, timeout_s=300.0, transport=http_post, safety_off=True, **kw,
    ):
        super().__init__(model, **kw)
        self.safety_off = safety_off
        self._key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")
        if not self._key:
            raise ValueError("GEMINI_API_KEY is not set")
        self.structured = structured
        self.system_role = system_role
        self.temperature = temperature
        self.timeout_s = timeout_s
        self.transport = transport

    def build_request(self, system, user, images, schema):
        parts = [] if self.system_role else [{"text": system}]
        parts.append({"text": user})
        for png in images:
            parts.append(
                {"inline_data": {"mime_type": "image/png",
                                 "data": base64.b64encode(png).decode("ascii")}}
            )
        body = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": self.temperature},
        }
        if self.system_role:
            body["system_instruction"] = {"parts": [{"text": system}]}
        if self.safety_off:
            body["safetySettings"] = [
                {"category": category, "threshold": "BLOCK_NONE"}
                for category in SAFETY_CATEGORIES
            ]
        if self.structured and schema is not None:
            body["generationConfig"]["responseMimeType"] = "application/json"
            body["generationConfig"]["responseSchema"] = to_gemini_schema(schema)
        headers = {"Content-Type": "application/json", "x-goog-api-key": self._key}
        return ENDPOINT.format(model=self.model), headers, body

    def parse_response(self, payload: dict) -> ModelResponse:
        usage = payload.get("usageMetadata") or {}
        input_tokens = int(usage.get("promptTokenCount", 0))
        output_tokens = int(usage.get("candidatesTokenCount", 0)) + int(
            usage.get("thoughtsTokenCount", 0)
        )
        spent = {"raw": payload, "input_tokens": input_tokens, "output_tokens": output_tokens}
        candidates = payload.get("candidates") or []
        if not candidates:
            block = (payload.get("promptFeedback") or {}).get("blockReason", "no_candidates")
            raise Fatal(f"blocked: {block}", **spent)
        first = candidates[0]
        finish = first.get("finishReason", "")
        if finish in BLOCKING_FINISH:
            raise Fatal(f"blocked: {finish}", **spent)
        if finish == "MAX_TOKENS":
            raise Fatal("truncated: MAX_TOKENS", **spent)
        parts = (first.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        return ModelResponse(
            text=text,
            parsed=None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_s=0.0,
            model_version=payload.get("modelVersion", self.model),
            raw=payload,
        )

    def _attempt(self, system, user, images, schema, tag):
        url, headers, body = self.build_request(system, user, images, schema)
        status, response_headers, raw = self.transport(
            url, headers, json.dumps(body).encode("utf-8"), self.timeout_s
        )
        return self.parse_response(check_status(status, response_headers, raw))
