"""A real language model behind the pipeline: OpenAI's Codex CLI (`codex exec`).

`CodexModel.chat` has the signature of `prototype/models/adapter.ChatModel.chat` and returns the same
dict, so the real specialists and Judge use it unchanged. Codex has no separate system prompt, so the
agent's system prompt and its user prompt are sent as one message, under two headings, with one added
line asking for the answer without running commands.

Each call is one `codex exec` run in an empty temporary directory with a read-only sandbox, no saved
session (`--ephemeral`) and no execpolicy rules; the evidence in a prompt is untrusted page content.
Answers are cached on disk by a hash of (model, system prompt, user prompt); `no_cache=True` calls
again. This uses the Codex login on this machine. The evaluated system used GPT-4o-mini.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

PREAMBLE = ("Do not run any command or open any file: everything you need is below. "
            "Reply with the JSON object only.")


class CodexError(RuntimeError):
    pass


class CodexModel:
    key_env = "(Codex login)"

    def __init__(self, model: str | None = None, cache_dir: Path | None = None, no_cache: bool = False,
                 timeout: int = 300):
        exe = shutil.which("codex")
        if not exe:
            raise SystemExit("The `codex` command (Codex CLI) is not on PATH. Install it, or use --cc, "
                             "--scripted, or the default GPT-4o-mini.")
        self.exe, self.model, self.timeout = exe, model, timeout
        self.spec = f"codex:{model or 'default'}"
        self.cache = Path(cache_dir) / (model or "default") if cache_dir else None
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)
        self.no_cache = no_cache

    def chat(self, system: str, user: str, max_tokens: int = 2048, json_mode: bool = False,
             images: list | None = None, temperature: float = 0, sample: int | None = None) -> dict:
        shas = [hashlib.sha256(Path(i).read_bytes()).hexdigest() for i in images or []]
        key = hashlib.sha256(json.dumps([self.spec, system, user, sample] + shas).encode()).hexdigest()
        path = self.cache / f"{key}.json" if self.cache else None
        cached = bool(path and path.exists() and not self.no_cache)
        t0 = time.time()
        if cached:
            rec = json.loads(path.read_text("utf-8"))
        else:
            rec = self._call(system, user, images or [])
            if path:
                path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), "utf-8")
        u = rec.get("usage") or {}
        return {"text": rec["result"], "finish_reason": "stop", "input_tokens": u.get("input_tokens", 0),
                "output_tokens": u.get("output_tokens", 0), "latency_s": round(time.time() - t0, 2),
                "request_sha": key, "model": self.spec, "cached": cached}

    def _call(self, system: str, user: str, images: list) -> dict:
        prompt = f"{PREAMBLE}\n\n# Instructions\n\n{system}\n\n# Input\n\n{user}\n"
        with tempfile.TemporaryDirectory(prefix="mazp-codex-") as d:
            last = Path(d) / "last.txt"
            cmd = [self.exe, "exec", "--skip-git-repo-check", "--ephemeral", "--ignore-rules",
                   "-s", "read-only", "-C", d, "--json", "-o", str(last), "--color", "never"]
            if self.model:
                cmd += ["-m", self.model]
            for n, img in enumerate(images):                 # attached with -i (copied beside the run)
                dst = Path(d) / f"image{n}.png"
                shutil.copy(img, dst)
                cmd += ["-i", str(dst)]
            cmd.append("-")
            try:
                r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=self.timeout, cwd=d)
            except subprocess.TimeoutExpired:
                raise CodexError(f"codex exec timed out after {self.timeout}s")
            text = last.read_text("utf-8") if last.exists() else ""
            if r.returncode or not text.strip():
                raise CodexError(f"codex exec failed (exit {r.returncode}): {(r.stderr or r.stdout)[-400:]}")
        usage = {}
        for line in r.stdout.splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "turn.completed":
                usage = ev.get("usage") or {}
        return {"result": text, "usage": usage, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "request": {"model": self.spec, "system": system, "user": user}}
