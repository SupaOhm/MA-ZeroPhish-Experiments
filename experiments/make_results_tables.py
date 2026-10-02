"""Markdown tables straight from evaluate.py outputs (metrics.csv, comparisons.csv) -- no
number is typed by hand. Used for experiments/RESULTS_GPT4OMINI.md.

    python experiments/make_results_tables.py <score_dir> [<title>]
"""
import csv
import sys
from pathlib import Path


def f(x, nd=3):
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return "–"


def table(score_dir: str, title: str = "") -> str:
    d = Path(score_dir)
    rows = [r for r in csv.DictReader((d / "metrics.csv").open(encoding="utf-8")) if r["subset"] == "all"]
    out = [f"**{title}**" if title else "", "",
           "| arm | n | decided (coverage) | precision* | recall* | F1* | FPR* | forced F1 | forced accuracy | selective risk | calls/case | in/out tokens per case | latency s/case |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: r["arm"]):
        out.append(f"| {r['arm']} | {r['n']} | {r['decided']} ({f(r['coverage'], 2)}) | {f(r['precision'])} | "
                   f"{f(r['recall'])} | {f(r['f1'])} | {f(r['fpr'])} | {f(r['forced_f1'])} | "
                   f"{f(r['forced_accuracy'])} | {f(r['selective_risk'])} | {f(r['mean_model_calls'], 1)} | "
                   f"{f(r['mean_input_tokens'], 0)} / {f(r['mean_output_tokens'], 0)} | {f(r['mean_latency_s'], 1)} |")
    out += ["", "\\* on decided cases only; forced metrics count `insufficient` as an error.", ""]
    cp = d / "comparisons.csv"
    comp = list(csv.DictReader(cp.open(encoding="utf-8"))) if cp.exists() else []
    if comp:
        out += ["| arm vs reference | paired n | Δ forced F1 [95% CI] | Δ coverage [95% CI] | McNemar p |",
                "|---|---|---|---|---|"]
        for c in comp:
            out.append(f"| {c['arm']} vs {c['reference']} | {c['n_paired']} | {f(c['forced_f1_delta'])} "
                       f"[{f(c['forced_f1_ci_low'])}, {f(c['forced_f1_ci_high'])}] | {f(c['coverage_delta'])} "
                       f"[{f(c['coverage_ci_low'])}, {f(c['coverage_ci_high'])}] | {f(c['mcnemar_p_value'])} |")
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    print(table(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""))
