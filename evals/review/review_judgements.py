"""
Writes JUDGEMENTS.md for a variant: each case's known issues, every review comment, and the
judge's verdict on it, for checking the grading.  python evals/review/review_judgements.py baseline
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from run import FLOW, load_cases


def main(variant: str) -> None:
    cases = {c["id"]: c for c in load_cases()}
    rows = [json.loads(l) for l in (FLOW / variant / "results.jsonl").read_text().splitlines()]
    out = [f"# Judge verdicts: {variant}", ""]
    for row in sorted(rows, key=lambda r: (r["prompt_id"], r["rep"])):
        case = cases[row["prompt_id"]]
        trace = json.loads((FLOW / variant / "traces" / f"{row['prompt_id']}_rep{row['rep']}.json").read_text())
        suggestions = json.loads(next(t for t in trace if t["role"] == "assistant")["content"])
        judged = next((json.loads(t["content"]) for t in trace if t["role"] == "tool_call"), {"verdicts": []})
        verdicts = {v["comment_id"]: v for v in judged["verdicts"]}
        g = row["grade"]
        out += [f"## {row['prompt_id']} (rep {row['rep']}): {'PASS' if g['case_pass'] else 'FAIL'}", ""]
        out.append("**Known issues:** " + ("none (clean)" if not case["issues"] else ""))
        for i in case["issues"]:
            where = ", ".join(f"{l['file']}:{l['lines'][0]}-{l['lines'][1]}" for l in i["locations"])
            hit = "found" if i["id"] in row["meta"]["majors_found_ids"] + row["meta"]["minors_found_ids"] else "not found"
            out.append(f"- {i['id']} ({hit}): {' '.join(i['description'].split())} [{where}]")
        shown = [s for s in suggestions if s["confidence"] >= 0.5]
        out += ["", f"**Comments ({len(shown)} shown, {len(suggestions) - len(shown)} below the confidence threshold):**", ""]
        for n, s in enumerate(shown, 1):
            v = verdicts.get(f"c{n}", {})
            label = v.get("verdict", "?") + (f" {v['known_issue_id']}" if v.get("known_issue_id") else "")
            lines = f"{s['line']}" + (f"-{s['end_line']}" if s.get("end_line") and s["end_line"] != s["line"] else "")
            out += [f"{n}. `{s['file_path']}:{lines}` [{s['severity']}, {s['confidence']}] **{s['title']}**",
                    f"   {s['explanation']}", f"   - **Judge: {label}**: {v.get('reason', '')}", ""]
    path = FLOW / variant / "JUDGEMENTS.md"
    path.write_text("\n".join(out) + "\n")
    print(f"wrote {path.relative_to(FLOW.parents[2])}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "baseline")
