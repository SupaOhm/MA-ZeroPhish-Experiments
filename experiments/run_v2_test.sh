#!/usr/bin/env bash
# PROTOCOL_V2.md step 4: run the declared test experiments ONCE for v2 and v2b (in parallel
# per experiment), into runs/<version>/expN. Resumable. Usage: bash experiments/run_v2_test.sh
set -uo pipefail
M="openrouter:openai/gpt-4o-mini-2024-07-18"
X='{"provider":{"order":["openai"],"allow_fallbacks":false,"data_collection":"deny"}}'
DV="d014eb0152251d9c"
C=(--model "$M" --env ../MA_ZeroPhish_VerAJ_Ohm/.env --extra "$X" --min-interval 0 --data-version "$DV")
step() {  # step <script> <outsub> [extra args...]
  local script="$1" sub="$2"; shift 2
  for V in v2 v2b; do
    for k in 0 1 2 3 4 5; do
      python -B "$script" "${C[@]}" --system-version "$V" --shard "$k/6" --out "runs/$V/$sub" "$@" \
        > "runs/${V}_${sub}_$k.log" 2>&1 &
    done
  done
  wait
  for V in v2 v2b; do
    echo "$sub $V: $(cat runs/${V}_${sub}_*.log | grep -c '\]: ') runs, errors: $(cat runs/${V}_${sub}_*.log | grep -cE 'Traceback|APIError|QuotaExhausted|REFUSED')"
  done
}
step experiments/exp1_detection/run_mazerophish.py exp1 --per-label 100
step experiments/exp4_collaboration/run_arms.py exp4
step experiments/exp6_ablations/run_ablations.py exp6
step experiments/exp5_robustness/run_conditions.py exp5 --conflicts 8
step experiments/exp2_selection/run_end_to_end.py exp2 --conditions complete matched_agent_2
echo "V2 TEST RUNS DONE"
