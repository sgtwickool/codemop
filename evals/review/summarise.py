"""
Summarises the review eval's results, a column per variant, and writes
.claude/hillclimb/review/SUMMARY.md. Run from the repository root after run.py:

    python evals/review/summarise.py

Costs are estimates from list prices (codemop.providers.pricing), for the review and the judge
separately: the judge is the eval's cost, not the user's.
"""
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from codemop.providers.base import Usage
from codemop.providers.pricing import ANTHROPIC_PRICES, PRICES_AS_OF
from run import FLOW, JUDGE_MODEL, VARIANTS


def wilson(passed: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """A 95% confidence interval for a pass rate"""
    if n == 0:
        return 0.0, 0.0
    p = passed / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - spread, centre + spread


def cost(model: str, usage: dict) -> float:
    return ANTHROPIC_PRICES[model].cost(Usage(usage["input_tokens"], usage["output_tokens"]))


def load(variant: str) -> tuple[list, list]:
    directory = FLOW / variant
    read = lambda name: [json.loads(line) for line in (directory / name).read_text().splitlines()] \
        if (directory / name).exists() else []
    return read("results.jsonl"), read("errors.jsonl")


def rate(rows: list) -> str:
    passed = sum(r["grade"]["case_pass"] for r in rows)
    low, high = wilson(passed, len(rows))
    return f"{passed}/{len(rows)} ({passed / len(rows):.0%}, {low:.0%}–{high:.0%})" if rows else "–"


def summarise(variant: str, rows: list, errors: list) -> dict:
    buggy = [r for r in rows if r["meta"]["majors_total"]]
    clean = [r for r in rows if not r["meta"]["majors_total"]]
    comments = sum(r["meta"]["comments"] for r in rows)
    false_alarms = sum(r["grade"]["false_alarms"] for r in rows)
    review_cost = [cost(VARIANTS[variant]["model"], r["usage"]) for r in rows]
    judge_cost = sum(cost(JUDGE_MODEL, r["judge_usage"]) for r in rows if r["judge_model"])
    latency = sorted(r["latency_s"] for r in rows)
    return {
        "Cases passed (95% CI)": rate(rows),
        "  simple cases": rate([r for r in rows if "simple" in r["tags"]]),
        "  complex cases": rate([r for r in rows if "complex" in r["tags"]]),
        "  buggy cases (all majors found)": rate(buggy),
        "  clean cases (no false alarms)": rate(clean),
        "Major issues found": f"{sum(r['grade']['majors_found'] for r in buggy)}/{sum(r['meta']['majors_total'] for r in buggy)}",
        "Minor issues found": f"{sum(len(r['meta']['minors_found_ids']) for r in rows)}/{sum(r['meta']['minors_total'] for r in rows)}",
        "Other real issues raised": str(sum(r["meta"]["other_real_issues"] for r in rows)),
        "False alarms (all cases)": str(false_alarms),
        "  on clean cases": str(sum(r["grade"]["false_alarms"] for r in clean)),
        "Comments that were right": f"{comments - false_alarms}/{comments} ({(comments - false_alarms) / comments:.0%})" if comments else "–",
        "Found in the wrong place": str(sum(len(r["meta"]["found_in_wrong_place"]) for r in rows)),
        "Review cost per case": f"${statistics.mean(review_cost):.4f}" if rows else "–",
        "Review cost, all runs": f"${sum(review_cost):.2f}",
        "Judge cost, all runs": f"${judge_cost:.2f}",
        "Latency, median / slowest": f"{statistics.median(latency):.0f}s / {latency[-1]:.0f}s" if rows else "–",
        "Refusals / truncated": f"{sum(r['meta'].get('failure_class') == 'refusal' for r in rows)} / {sum(r['status'] == 'truncated' for r in rows)}",
        "Errors (nothing to grade)": str(len(errors)),
    }


def per_case(results: dict) -> list:
    """Each case's pass count per variant, for the cases where the variants disagree"""
    passes = defaultdict(dict)
    tags = {}
    for variant, rows in results.items():
        for r in rows:
            passes[r["prompt_id"]].setdefault(variant, []).append(r["grade"]["case_pass"])
            tags[r["prompt_id"]] = r["tags"][1]
    lines = []
    for case, by_variant in sorted(passes.items()):
        counts = {v: f"{sum(p)}/{len(p)}" for v, p in by_variant.items()}
        if len(set(counts.values())) > 1:
            lines.append(f"| {case} ({tags[case]}) | " + " | ".join(counts.get(v, "–") for v in results) + " |")
    return lines


def main() -> None:
    results, summaries = {}, {}
    for variant in VARIANTS:
        rows, errors = load(variant)
        if rows:
            results[variant] = rows
            summaries[variant] = summarise(variant, rows, errors)
    header = "| | " + " | ".join(f"{v}: {VARIANTS[v]['label']}" for v in summaries) + " |"
    divider = "|---" * (len(summaries) + 1) + "|"
    out = ["# Review eval: summary", "", f"Prices as of {PRICES_AS_OF}; judge {JUDGE_MODEL}.", "", header, divider]
    for metric in next(iter(summaries.values())):
        out.append(f"| {metric} | " + " | ".join(s[metric] for s in summaries.values()) + " |")
    out += ["", "## Cases the variants disagree on (passes / runs)", "",
            "| case | " + " | ".join(results) + " |", "|---" * (len(results) + 1) + "|", *per_case(results)]
    text = "\n".join(out) + "\n"
    (FLOW / "SUMMARY.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
