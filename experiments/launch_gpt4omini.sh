#!/usr/bin/env bash
# GPT-4o-mini runs, in the order frozen in experiments/exp1_detection/PROTOCOL_GPT4OMINI.md.
# Usage (from the repo root):  bash experiments/launch_gpt4omini.sh <step> <DATA_VERSION>
# Steps: pilot | exp1_baselines | exp4_collect | exp4_freeze | exp1_mazero | exp4_arms |
#        exp6 | exp5 | exp2 | cost
# Every step is resumable (re-run the same command); API errors are never scored; a spent
# OpenRouter budget (HTTP 402) stops the run cleanly.
set -euo pipefail
STEP="${1:?step}"; DV="${2:-}"
MODEL="openrouter:openai/gpt-4o-mini-2024-07-18"
EXTRA='{"provider":{"order":["openai"],"allow_fallbacks":false,"data_collection":"deny"}}'
ENV="../MA_ZeroPhish_VerAJ_Ohm/.env"
PP="experiments/data_eval/data/phreshphish"
N="${SHARDS:-6}"               # parallel processes (OpenRouter has no daily quota)
COMMON=(--model "$MODEL" --env "$ENV" --extra "$EXTRA" --min-interval 0.5)
need_dv() { [ -n "$DV" ] || { echo "DATA_VERSION required"; exit 1; }; }
par() {  # run "$@ --shard k/N" for k in 0..N-1 in parallel, wait for all
  for k in $(seq 0 $((N-1))); do "$@" --shard "$k/$N" & done; wait; }

case "$STEP" in
  pilot)          need_dv   # 5 calib cases through the full system + 5 dev cases per baseline
    python -B experiments/exp4_collaboration/collect_states.py "${COMMON[@]}" --data-version "$DV" --limit 5
    for arm in single_agent cot phishdebate; do
      python -B experiments/exp1_detection/run_baselines.py --arm $arm --data $PP --split dev --limit 5 \
        --model "$MODEL" --env "$ENV" --extra "$EXTRA" --min-interval 0.5 --data-version "$DV" --out runs/pilot_gpt4omini
    done
    python -B experiments/cost_report.py runs/exp4 runs/pilot_gpt4omini ;;
  exp1_baselines) need_dv
    for arm in single_agent cot phishdebate; do
      python -B experiments/exp1_detection/run_baselines.py --arm $arm --data $PP --split test \
        --model "$MODEL" --env "$ENV" --extra "$EXTRA" --min-interval 0.5 --workers 4 --data-version "$DV" --out runs/exp1 &
    done; wait ;;
  exp4_collect)   need_dv; par python -B experiments/exp4_collaboration/collect_states.py "${COMMON[@]}" --data-version "$DV" ;;
  exp4_freeze)
    python -B experiments/exp4_collaboration/train_estimator.py --states $(ls runs/exp4/calib_states__all_fields*.jsonl | grep -v __ledger) \
      --manifest $PP/manifest.jsonl --out runs/exp4/estimator__gpt4omini.json
    python -B experiments/exp4_collaboration/freeze_gate.py --estimator runs/exp4/estimator__gpt4omini.json --model "$MODEL" ;;
  exp1_mazero)    need_dv; par python -B experiments/exp1_detection/run_mazerophish.py "${COMMON[@]}" --data-version "$DV" --per-label 100 ;;
  exp4_arms)      need_dv; par python -B experiments/exp4_collaboration/run_arms.py "${COMMON[@]}" --data-version "$DV" ;;
  exp6)           need_dv; par python -B experiments/exp6_ablations/run_ablations.py "${COMMON[@]}" --data-version "$DV" ;;
  exp5)           need_dv; par python -B experiments/exp5_robustness/run_conditions.py "${COMMON[@]}" --data-version "$DV" --conflicts 8 ;;
  exp2)           need_dv; par python -B experiments/exp2_selection/run_end_to_end.py "${COMMON[@]}" --data-version "$DV" --conditions complete matched_agent_2 ;;
  cost)           python -B experiments/cost_report.py runs ;;
  *) echo "unknown step $STEP"; exit 1 ;;
esac
