"""The raw call log: one JSON line per attempt, appended as it happens.

A result without its raw log is not a result (data_eval HANDOFF §0 rule 4), so
this is written before anything is parsed downstream and is never rewritten.
Headers are not logged, so credentials never reach it.
"""

import json
from datetime import datetime, timezone


class CallLog:
    def __init__(self, path: str, context: dict | None = None):
        self._handle = open(path, "a", encoding="utf-8")
        self.context = dict(context or {})

    def write(self, entry: dict) -> None:
        record = {"ts": datetime.now(timezone.utc).isoformat(), **self.context, **entry}
        self._handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
