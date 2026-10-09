from codemop.review.learned import HEADER, Dismissed, Learned, Settled, add_learned, parse_learned
from codemop.review.schema import ModelSuggestion, Severity

ENTRY = Learned("app.py", "Adds one to the total", "The +1 is the header row", "#7, @sam")


def suggestion(path="app.py", line=3, severity="bug", title="t"):
    return ModelSuggestion(file_path=path, line=line, severity=severity, title=title, explanation="e",
                           suggested_code=None, confidence=0.9)


def test_a_new_file_starts_with_a_header_saying_what_it_is():
    text = add_learned(None, ENTRY)

    assert text.startswith(HEADER)
    assert parse_learned(text) == [ENTRY]


def test_entries_are_added_without_touching_whats_there():
    mine = "# Our notes\n- path: x.py   # keep this comment\n  issue: A\n  reason: B\n"

    text = add_learned(mine, ENTRY)

    assert text.startswith(mine)
    assert [e.issue for e in parse_learned(text)] == ["A", "Adds one to the total"]


def test_a_hand_edited_file_with_mistakes_doesnt_stop_reviews():
    assert parse_learned("- just a string\n- path: x.py\n  issue: Only an issue\n- {issue: A, reason: B}\n") == [
        Learned("", "A", "B", "")
    ]
    assert parse_learned("not: [valid") == []
    assert parse_learned("{a: mapping}") == []
    assert parse_learned(None) == []


def test_long_text_is_cut_short():
    [entry] = parse_learned(f"- issue: A\n  reason: {'x' * 5000}\n")
    assert len(entry.reason) == 300


def test_nothing_settled_adds_no_instructions():
    assert Settled().instructions() == ""


def test_a_dismissed_issue_is_recognised_by_the_same_rule_as_an_earlier_finding():
    settled = Settled(dismissed=[Dismissed("app.py", 10, Severity.bug, "Off by one in the loop")])

    assert settled.dismisses(suggestion(line=40, title="Off by one in the loop"))  # same title, anywhere in the file
    assert settled.dismisses(suggestion(line=12, title="The loop is off by one"))  # nearby, reworded
    assert not settled.dismisses(suggestion(line=11, title="Unvalidated input reaches the query"))  # a different bug
    assert not settled.dismisses(suggestion(path="other.py", line=10, title="Off by one in the loop"))
    assert not settled.dismisses(suggestion(line=10, severity="security", title="Off by one in the loop"))
