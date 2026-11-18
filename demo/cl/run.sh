#!/usr/bin/env bash
# Run the MA-ZeroPhish terminal demo. Creates .venv on first use.
#   ./run.sh                          GPT-4o-mini (the evaluated model); key from OPENROUTER_API_KEY or
#                                     OPENAI_API_KEY in the environment, or --env <file>
#   ./run.sh --cc                     Claude through Claude Code (`claude -p`); --cc-model sonnet|opus
#   ./run.sh --cdx                    Codex (`codex exec`); --cdx-model <model>
#   ./run.sh --scripted               offline rule list, no model, no network
#   ./run.sh --url <url>              acquire a URL's evidence live (GET, offline render, CT, RDAP,
#                                     DNS, TLS) and analyze it; --no-fetch: the URL string only
#   ./run.sh --case bank-login        one bundled case (bank-login | library-site | parcel-fee)
#   ./run.sh --quiet                  hide each finding's reasoning; --no-cache to call the model again
# The full JSON trace of each case goes to runs/demo-cl/<case>.trace.json.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
if [ ! -x .venv/bin/python ]; then
  echo "First run: creating .venv and installing requirements..."
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/python -B demo/cl/demo.py "$@"
