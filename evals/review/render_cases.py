"""
Writes CASES.md: every case's diff and expected issues, for reviewing the case set.
Run from the repository root: python evals/review/render_cases.py
"""
import re
from pathlib import Path

import yaml

HERE = Path(__file__).parent


def fence(text: str) -> str:
    """A code fence longer than any run of backticks in the text"""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def main():
    cases = yaml.safe_load((HERE / "cases.yml").read_text())
    out = [
        "# Review eval cases",
        "",
        "Generated from `cases.yml` and `cases/` by `render_cases.py`. Line numbers are new-file lines.",
        "",
        "| # | id | kind | expected issues |",
        "|---|----|------|-----------------|",
    ]
    for n, case in enumerate(cases, 1):
        majors = sum(1 for i in case["issues"] if i["severity"] == "major")
        minors = len(case["issues"]) - majors
        expected = "none (clean)" if not case["issues"] else f"{majors} major, {minors} minor"
        out.append(f"| {n} | [{case['id']}](#{case['id']}) | {case['tags'][0]} | {expected} |")
    for n, case in enumerate(cases, 1):
        diff = (HERE / "cases" / f"{case['id']}.diff").read_text()
        out += ["", f"## {case['id']}", "", f"**{n}. {', '.join(case['tags'])}**" + (f" · {case['source']}" if case.get("source") else ""), ""]
        if not case["issues"]:
            out.append("Expected: nothing wrong.")
        for issue in case["issues"]:
            where = "; ".join(f"`{l['file']}` lines {l['lines'][0]}-{l['lines'][1]}" for l in issue["locations"])
            out.append(f"- **{issue['severity']}**: {issue['description']} ({where})")
        f = fence(diff)
        out += ["", f + "diff", diff.rstrip("\n"), f]
    (HERE / "CASES.md").write_text("\n".join(out) + "\n")
    print(f"wrote CASES.md ({len(cases)} cases)")


if __name__ == "__main__":
    main()
