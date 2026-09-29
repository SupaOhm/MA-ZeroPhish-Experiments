"""The per-run ledger: one JSON object per line, written as the run happens.

His metric set is what dictates the columns. Paired confidence intervals need
every event keyed to a case and an arm; cost per case needs acquisition requests,
model calls, tokens and money counted at the moment they are incurred. None of it
is reconstructible afterwards, which is why this exists before any metric does.
"""

import json


class Ledger:
    def __init__(self, path: str, arm: str, mode: str = "w"):
        # "a" for a resumed corpus run: earlier cases' events are kept.
        self._handle = open(path, mode, encoding="utf-8")
        self._arm = arm

    def event(self, kind: str, case_id: str, **payload) -> None:
        record = {"kind": kind, "arm": self._arm, "case_id": case_id}
        record.update(payload)
        self._handle.write(json.dumps(record, sort_keys=True) + "\n")

    def flush(self) -> None:
        """Push written events to disk: a killed run loses at most the case in flight."""
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def read(path: str) -> tuple[dict, ...]:
    with open(path, encoding="utf-8") as handle:
        return tuple(json.loads(line) for line in handle if line.strip())
