from codemop.review.chunks import estimate_tokens, plan_chunks
from codemop.review.diff import parse_diff
from codemop.review.prompt import render_file, render_hunks


def test_skips_what_isnt_worth_reviewing(sample_diff):
    plan = plan_chunks(parse_diff(sample_diff), budget_tokens=10_000)

    assert {(s.path, s.reason) for s in plan.skipped} == {
        ("old.txt", "deleted file"),
        ("docs/b.md", "no changed lines (rename only)"),
        ("logo.png", "binary file"),
        ("uv.lock", "matches an ignored path pattern"),
    }
    assert [f.path for chunk in plan.chunks for f in chunk.files] == ["app/service.py", "app/new_module.py"]


def test_small_files_share_a_chunk(sample_diff):
    plan = plan_chunks(parse_diff(sample_diff), budget_tokens=10_000)

    assert len(plan.chunks) == 1
    assert "### app/service.py" in plan.chunks[0].text
    assert "### app/new_module.py" in plan.chunks[0].text


def test_files_go_into_separate_chunks_when_the_budget_is_reached(sample_diff):
    files = parse_diff(sample_diff)
    service = next(f for f in files if f.path == "app/service.py")

    plan = plan_chunks(files, budget_tokens=estimate_tokens(render_file(service)))

    assert [[f.path for f in chunk.files] for chunk in plan.chunks] == [["app/service.py"], ["app/new_module.py"]]
    assert all(chunk.tokens <= estimate_tokens(render_file(service)) for chunk in plan.chunks)


def test_a_large_file_is_split_by_hunk(sample_diff):
    files = parse_diff(sample_diff)
    service = next(f for f in files if f.path == "app/service.py")
    largest_hunk = max(estimate_tokens(render_hunks(service, [h])) for h in service.hunks)

    plan = plan_chunks([service], budget_tokens=largest_hunk)

    assert len(plan.chunks) == 2
    assert [c.text.count("@@") for c in plan.chunks] == [2, 2]  # one hunk header each (opening and closing @@)
    assert plan.skipped == []


def test_a_hunk_too_large_for_any_chunk_is_reported(sample_diff):
    service = next(f for f in parse_diff(sample_diff) if f.path == "app/service.py")
    small_hunk = min(estimate_tokens(render_hunks(service, [h])) for h in service.hunks)

    plan = plan_chunks([service], budget_tokens=small_hunk)

    assert len(plan.chunks) == 1
    [skipped] = plan.skipped
    assert skipped.path == "app/service.py"
    assert skipped.reason.startswith("hunk too large to review: @@ -10,6 +10,7 @@")


def test_custom_ignored_paths(sample_diff):
    plan = plan_chunks(parse_diff(sample_diff), budget_tokens=10_000, ignored_paths=["app/new_*"])

    assert ("app/new_module.py", "matches an ignored path pattern") in {(s.path, s.reason) for s in plan.skipped}
    assert "uv.lock" not in {s.path for s in plan.skipped}  # the defaults are replaced
