"""
Tests for turning an AI response into suggestions: one place validates them, and
nothing is made up for a suggestion that doesn't say where or what.
"""
import json

from app.utils.parsing import parse_ai_response


def response(*suggestions) -> str:
    return json.dumps({"suggestions": list(suggestions)})


COMPLETE = {"line_number": 4, "file_path": "app.py", "description": "Null check", "fix": "if x:", "confidence": 0.8}


def test_complete_suggestions_are_kept():
    assert parse_ai_response(response(COMPLETE)) == [COMPLETE]


def test_incomplete_suggestions_are_dropped_not_filled_in():
    incomplete = [
        {**COMPLETE, "file_path": None},
        {k: v for k, v in COMPLETE.items() if k != "file_path"},
        {k: v for k, v in COMPLETE.items() if k != "line_number"},
        {**COMPLETE, "line_number": "four"},
        {**COMPLETE, "description": ""},
        "not an object",
    ]

    assert parse_ai_response(response(COMPLETE, *incomplete)) == [COMPLETE]


def test_optional_fields_get_defaults():
    minimal = {"line_number": 1, "file_path": "a.py", "description": "Issue", "confidence": None}

    [suggestion] = parse_ai_response(response(minimal))

    assert suggestion["fix"] == "No fix provided"
    assert suggestion["confidence"] == 0.5


def test_unexpected_json_shapes_give_no_suggestions():
    assert parse_ai_response(json.dumps([COMPLETE])) == []
    assert parse_ai_response(json.dumps({"suggestions": "none"})) == []


def test_text_fallback_goes_through_the_same_validation():
    text = "Line number 12\nIssue: Unused import\nFile: app.py\n\nLine number unknown\nIssue: No location\nFile: app.py"

    assert parse_ai_response(text) == [{
        "line_number": 12,
        "file_path": "app.py",
        "description": "Unused import",
        "fix": "No fix provided",
        "confidence": 0.7,
    }]
