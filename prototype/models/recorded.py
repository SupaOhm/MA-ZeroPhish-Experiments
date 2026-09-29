"""A client that serves recorded replies. **For tests only.**

Its default model id, `recorded-fixture`, is on `evaluate.py`'s simulated list,
so a ledger produced with it can never be scored as a result. Token counts are
character counts, not a tokenizer's: they exist so the columns are non-zero.
"""

import json

from .client import BaseClient, Fatal, ModelResponse

TAG_FIELDS = ("case_id", "object_id", "role", "phase")


def tag_key(tag: dict) -> str:
    return "|".join(str(tag.get(name, "")) for name in TAG_FIELDS)


class RecordedClient(BaseClient):
    provider = "recorded"

    def __init__(self, responses, model: str = "recorded-fixture", **kw):
        kw.setdefault("sleep", lambda seconds: None)
        super().__init__(model, **kw)
        self._responses = responses
        self.requests: list[dict] = []

    def _attempt(self, system, user, images, schema, tag):
        self.requests.append(
            {"system": system, "user": user, "images": images, "schema": schema, "tag": tag}
        )
        if callable(self._responses):
            reply = self._responses(tag, system, user, images)
        else:
            key = tag_key(tag)
            if key not in self._responses:
                raise Fatal(f"no_recording: {key}")
            reply = self._responses[key]
        if isinstance(reply, Exception):
            raise reply
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return ModelResponse(
            text=text,
            parsed=None,
            input_tokens=len(system) + len(user),
            output_tokens=len(text),
            latency_s=0.0,
            model_version=self.model,
        )
