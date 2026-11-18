"""A real language model behind the pipeline: Claude, called through the Claude Code CLI.

`ClaudeCodeModel.chat` has the signature of `prototype/models/adapter.ChatModel.chat` and returns the
same dict, so the real specialists (`agents/llm.py`) and Judge (`phases/judge_llm.py`) use it
unchanged: the prompts are theirs, byte for byte, and so are the checks on the answers.

Each call is one headless `claude -p` run with the agent's system prompt and its user prompt on
stdin, and with everything else switched off: no tools (`--tools ""`), no MCP servers, no user or
project settings (so no hooks and no CLAUDE.md), no saved session, run from an empty directory. The
evidence in a prompt is untrusted page content; with no tools, an instruction hidden in it can do
nothing but change the answer, which the code then checks.

Answers are cached on disk by a hash of (model, system prompt, user prompt), as the real runner caches
its OpenRouter answers, so a repeated run of the same case reads the cache. Use `no_cache=True` to
call the model again.

This uses the Claude Code login on this machine. The evaluated system used GPT-4o-mini; results from
Claude are a demonstration, not the system's measured performance.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

class ClaudeCodeError(RuntimeError):
    pass


class ClaudeCodeModel:
    key_env = "(Claude Code login)"

    def __init__(self, model: str = "haiku", cache_dir: Path | None = None, no_cache: bool = False,
                 timeout: int = 180):
        exe = shutil.which("claude")
        if not exe:
            raise SystemExit("The `claude` command (Claude Code) is not on PATH. Install it, or use --cdx, "
                             "--scripted, or the default GPT-4o-mini.")
        self.exe, self.model, self.timeout = exe, model, timeout
        self.spec = f"claude-code:{model}"
        self.cache = Path(cache_dir) / model if cache_dir else None
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)
        self.no_cache = no_cache
        self._cwd = tempfile.mkdtemp(prefix="mazp-claude-")

    def chat(self, system: str, user: str, max_tokens: int = 2048, json_mode: bool = False,
             images: list | None = None, temperature: float = 0, sample: int | None = None) -> dict:
        shas = [hashlib.sha256(Path(i).read_bytes()).hexdigest() for i in images or []]
        key = hashlib.sha256(json.dumps([self.model, system, user, sample] + shas).encode()).hexdigest()
        path = self.cache / f"{key}.json" if self.cache else None
        cached = bool(path and path.exists() and not self.no_cache)
        t0 = time.time()
        if cached:
            rec = json.loads(path.read_text("utf-8"))
        else:
            rec = self._call(system, user, images or [])
            if path:
                path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), "utf-8")
        text = rec["result"]
        usage = rec.get("usage") or {}
        tokens_in = sum(usage.get(k, 0) or 0 for k in ("input_tokens", "cache_creation_input_tokens",
                                                       "cache_read_input_tokens"))
        tokens_out = usage.get("output_tokens", 0) or 0
        return {"text": text, "finish_reason": rec.get("stop_reason"), "input_tokens": tokens_in,
                "output_tokens": tokens_out, "latency_s": round(time.time() - t0, 2), "request_sha": key,
                "model": self.spec, "cached": cached}

    def _call(self, system: str, user: str, images: list) -> dict:
        cmd = [self.exe, "-p", "--model", self.model, "--system-prompt", system, "--tools", "",
               "--strict-mcp-config", "--setting-sources", "", "--no-session-persistence"]
        if images:
            # An image goes in as a content block of a stream-json user message (no tool needed).
            content = [{"type": "text", "text": user}] + [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                             "data": base64.b64encode(Path(i).read_bytes()).decode()}}
                for i in images]
            cmd += ["--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
            stdin = json.dumps({"type": "user", "message": {"role": "user", "content": content}}) + "\n"
        else:
            cmd += ["--output-format", "json"]
            stdin = user
        try:
            r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=self.timeout,
                               cwd=self._cwd)
        except subprocess.TimeoutExpired:
            raise ClaudeCodeError(f"claude -p timed out after {self.timeout}s")
        try:
            if images:
                out = next(e for e in map(json.loads, r.stdout.splitlines()) if e.get("type") == "result")
            else:
                out = json.loads(r.stdout)
        except (json.JSONDecodeError, StopIteration):
            raise ClaudeCodeError(f"claude -p failed (exit {r.returncode}): {(r.stderr or r.stdout)[:400]}")
        if out.get("is_error") or out.get("subtype") != "success":
            raise ClaudeCodeError(f"claude -p error: {str(out.get('result') or out)[:400]}")
        used = next(iter(out.get("modelUsage") or {}), self.model)
        return {"result": out.get("result", ""), "usage": out.get("usage"), "stop_reason": out.get("stop_reason"),
                "model_used": used, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "request": {"model": self.model, "system": system, "user": user}}
