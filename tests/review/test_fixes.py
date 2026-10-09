from codemop.review.diff import parse_diff
from codemop.review.fixes import Fix, apply_fixes, file_lines, fit_fix
from codemop.review.schema import ModelSuggestion

# The start of PR #2's test_code.py, as an added file (new-file lines 1-15)
SOURCE = '''\
#!/usr/bin/env python3

# Simple Python code with some intentional issues for AI to find

def calculate_average(numbers):
    """Calculate average of numbers - has a bug!"""
    if len(numbers) == 0:
        return 0  # Bug: Should probably return None or raise exception

    total = 0
    for num in numbers:
        total += num

    average = total / len(numbers)  # Potential division by zero if not checked properly
    return average
'''
LINES = file_lines(parse_diff(
    "diff --git a/test_code.py b/test_code.py\nnew file mode 100644\n--- /dev/null\n+++ b/test_code.py\n"
    f"@@ -0,0 +1,{len(SOURCE.splitlines())} @@\n" + "".join(f"+{line}\n" for line in SOURCE.splitlines())
)[0])


def fix(code, line=8, end_line=None):
    return ModelSuggestion(file_path="test_code.py", line=line, end_line=end_line, severity="bug", title="t",
                           explanation="e", suggested_code=code, confidence=0.9)


def test_no_fix():
    assert fit_fix(fix(None), LINES) == (None, None)


def test_a_fix_that_fits_is_kept_as_it_is():
    code = '        raise ValueError("no numbers to average")'
    assert fit_fix(fix(code), LINES) == (code, None)


def test_a_fix_spanning_several_lines_is_kept():
    code = '    if not numbers:\n        raise ValueError("no numbers to average")'
    assert fit_fix(fix(code, line=7, end_line=8), LINES) == (code, None)


def test_the_line_above_repeated_at_the_start_is_trimmed():
    code = '    if len(numbers) == 0:\n        raise ValueError("no numbers to average")'
    assert fit_fix(fix(code), LINES) == ('        raise ValueError("no numbers to average")', None)


def test_the_line_below_repeated_at_the_end_is_trimmed():
    code = '        raise ValueError("no numbers to average")\n    \n    total = 0'
    assert fit_fix(fix(code), LINES) == ('        raise ValueError("no numbers to average")', None)


def test_a_whole_function_rewrite_for_one_line_is_left_out():
    """What qwen2.5-coder:7b suggested for line 8 of PR #2: applied, it would duplicate the function's body"""
    code = '''\
def calculate_average(numbers):
    """Calculate average of numbers - has a bug!"""
    if len(numbers) == 0:
        raise ValueError("List is empty")
    total = 0
    for num in numbers:
        total += num
    average = total / len(numbers)
    return average'''

    fixed, problem = fit_fix(fix(code), LINES)

    assert fixed is None
    assert "repeats a nearby line" in problem


def test_a_fix_that_changes_nothing_is_left_out():
    code = "        return 0  # Bug: Should probably return None or raise exception"
    assert fit_fix(fix(code), LINES) == (None, "it's the same as the current code")


def test_a_fix_that_only_repeats_the_surrounding_lines_is_left_out():
    assert fit_fix(fix("    if len(numbers) == 0:", line=8), LINES) == (None, "it only repeats the lines around the issue")


def test_short_lines_can_repeat():
    """Blank lines, brackets, `else:` legitimately appear both in a fix and next to it"""
    code = '    if not numbers:\n    \n        raise ValueError("no numbers to average")'
    assert fit_fix(fix(code, line=7, end_line=8), LINES) == (code, None)


def test_a_repeat_of_the_next_line_at_the_end_is_trimmed():
    code = "    if not numbers:\n        return None\n    return total / len(numbers)\n    return average"
    assert fit_fix(fix(code, line=14), LINES) == (code.removesuffix("\n    return average"), None)


def test_a_repeated_line_that_cant_be_trimmed_leaves_the_fix_out():
    """Applied at line 14, this would leave two `return average` lines"""
    code = "    average = sum(numbers) / len(numbers)\n    return average\n    print(average)"
    assert fit_fix(fix(code, line=14), LINES) == (
        None, "it repeats a nearby line ('return average'), which applying it would duplicate"
    )


def test_lines_the_diff_doesnt_show_cant_be_checked_so_the_fix_is_kept():
    code = "    x = compute()\n    y = other()"
    assert fit_fix(fix(code, line=40), LINES) == (code, None)


SAMPLE = "def total(items):\n    result = sum(items)\n    return result + 1\n"


def stored(code="    return result", line=3, original=("    return result + 1",), fix_id=1):
    return Fix(id=fix_id, path="app.py", line=line, end_line=line + len(original) - 1, code=code,
               original=list(original), title="Adds one")


def test_applies_a_fix_where_it_was_reviewed():
    result = apply_fixes(SAMPLE, [stored()])

    assert result.text == "def total(items):\n    result = sum(items)\n    return result\n"
    assert [f.id for f in result.applied] == [1] and result.skipped == []


def test_finds_the_lines_if_the_file_has_moved_on():
    moved = "import math\n\n" + SAMPLE

    result = apply_fixes(moved, [stored()])

    assert result.text == "import math\n\ndef total(items):\n    result = sum(items)\n    return result\n"


def test_skips_a_fix_whose_lines_have_changed():
    changed = SAMPLE.replace("result + 1", "result + 2")

    result = apply_fixes(changed, [stored()])

    assert result.text == changed
    assert [reason for _, reason in result.skipped] == ["the code it replaces has changed since it was reviewed"]


def test_skips_a_fix_whose_lines_now_appear_twice():
    """The file moved on, and the line to replace is now in two places: which one is ambiguous"""
    result = apply_fixes("# moved\n" + SAMPLE + SAMPLE, [stored()])

    assert result.applied == []
    assert [reason for _, reason in result.skipped] == ["the code it replaces has changed since it was reviewed"]


def test_applies_several_fixes_in_one_file_and_skips_overlaps():
    fixes = [stored(), stored(code="    result = sum(items or [])", line=2, original=("    result = sum(items)",), fix_id=2),
             stored(code="    pass", line=2, original=("    result = sum(items)", "    return result + 1"), fix_id=3)]

    result = apply_fixes(SAMPLE, fixes)

    assert result.text == "def total(items):\n    result = sum(items or [])\n    return result\n"
    assert [f.id for f in result.applied] == [2, 1]
    assert [(f.id, reason) for f, reason in result.skipped] == [(3, "it overlaps another fix being applied")]


def test_keeps_the_files_line_endings_and_odd_characters():
    crlf = SAMPLE.replace("\n", "\r\n").replace("def total", "\fdef total")

    result = apply_fixes(crlf, [stored()])

    assert result.text == "\fdef total(items):\r\n    result = sum(items)\r\n    return result\r\n"


def test_a_fix_can_replace_one_line_with_several():
    result = apply_fixes(SAMPLE, [stored(code="    if not items:\n        return 0\n    return result")])

    assert result.text.endswith("    if not items:\n        return 0\n    return result\n")
