"""
Checks that the judge rejects comments it must reject (a few API calls, a few cents):
    python evals/review/judge_checks.py
Each comment sits on the known issue's line, so only its content can make it fail.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import anthropic

from run import judge, load_cases

BAD_COMMENTS = {
    "empty": ("", ""),
    "i don't know": ("I'm not sure", "I don't know whether there's a problem here."),
    "wrong problem": (
        "Add a LIMIT to bound the result size",
        "This query can return unbounded rows; add a LIMIT clause so a broad search can't return millions of users.",
    ),
}


async def main() -> int:
    case = next(c for c in load_cases(["seeded-sql-injection"]))
    client = anthropic.AsyncAnthropic()
    failures = 0
    for name, (title, explanation) in BAD_COMMENTS.items():
        comment = {"id": "c1", "file_path": "store/users.py", "line": 11, "end_line": None, "severity": "bug",
                   "title": title, "explanation": explanation, "suggested_code": None}
        judgement, _ = await judge(client, case, [comment])
        verdict = judgement.verdicts[0]
        ok = verdict.verdict == "false_alarm"
        failures += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {name!r}: {verdict.verdict} ({verdict.reason})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
