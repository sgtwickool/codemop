"""A review's report, as text for people or JSON for scripts."""
import dataclasses
import json
import textwrap
from enum import Enum
from typing import List, Optional

from codemop.providers.base import Usage
from codemop.providers.pricing import PRICES_AS_OF
from codemop.review.pipeline import ReviewReport
from codemop.review.schema import location_text


def _to_jsonable(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value):
        return {f.name: _to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, Enum):
        return value.value
    return value


def report_json(report: ReviewReport, target: str, config_source: str) -> str:
    return json.dumps(
        {"target": target, "config": config_source, "complete": report.complete, **_to_jsonable(report)},
        indent=2,
    )


def format_cost(cost: Optional[float], usage: Usage) -> str:
    if not usage.input_tokens and not usage.output_tokens:
        return "nothing spent"
    if cost is None:
        return "cost unknown for this model"
    if cost == 0:
        return "no cost (local model)"
    return f"about ${cost:.2f}" if cost >= 0.01 else "under $0.01"


def report_text(report: ReviewReport, target: str, config_source: str) -> str:
    settings = "" if config_source == "defaults" else f" (settings from {config_source})"
    lines: List[str] = [f"CodeMop review of {target} with {report.model}{settings}", ""]
    if report.too_large:
        lines.append(f"Not reviewed: {report.too_large}.")
    elif not report.suggestions:
        lines.append("No issues found." if report.complete else "No issues found in the parts that were reviewed.")
    for s in report.suggestions:
        location = location_text(s.file_path, s.line, s.end_line)
        lines.append(f"{location}  [{s.severity.value}, confidence {s.confidence:.2f}]  {s.title}")
        lines.extend(textwrap.wrap(s.explanation, width=88, initial_indent="    ", subsequent_indent="    "))
        if s.suggested_code:
            lines.append("    Suggested change:")
            lines.extend("      " + code_line for code_line in s.suggested_code.splitlines())
        lines.append("")

    notes: List[str] = []
    # The chunk that hit the fatal error, and those not started after it, share one note
    stopped = [f for f in report.failed if report.stopped and (f.kind == "not_reviewed" or f.reason == report.stopped)]
    if stopped:
        paths = ", ".join(path for failed in stopped for path in failed.paths)
        notes.append(f"Stopped early: {report.stopped} (not reviewed: {paths})")
    notes += [f"Not reviewed ({', '.join(f.paths)}): {f.reason}" for f in report.failed if f not in stopped]
    notes += report.notes()
    if notes:
        lines += notes + [""]

    u = report.usage
    lines.append(f"{len(report.suggestions)} suggestion(s) · {report.chunks} chunk(s) · "
                 f"{u.input_tokens:,} input / {u.output_tokens:,} output tokens · "
                 f"{format_cost(report.cost, u)}" + ("" if not report.cost else f" (list prices as of {PRICES_AS_OF})"))
    return "\n".join(lines)
