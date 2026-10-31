from test_views import run, setup


def test_cycle_report_writes_escaped_html(tmp_path):
    root = setup(tmp_path)
    run("module", "add", "Vault", cwd=root)
    run("cycle", "add", "Sprint 1", "--start", "2026-10-01", "--end", "2026-10-14", cwd=root)
    run("task", "add", "Note editor", "--module", "vault", "--cycle", "sprint-1", "--estimate", "3h", "--status", "done", cwd=root)
    run("task", "add", "<script>alert(1)</script>", "--module", "vault", "--cycle", "sprint-1", "--estimate", "1h", cwd=root)

    result = run("cycle", "report", "sprint-1", "--out", "r.html", cwd=root)
    assert result.returncode == 0, result.stderr
    page = (root / "r.html").read_text()
    assert "NOD-1" in page and "NOD-2" in page
    assert "&lt;script&gt;" in page and "<script>" not in page
    assert "75%" in page  # 3h done of 4h


def test_cycle_report_unknown_cycle(tmp_path):
    root = setup(tmp_path)
    result = run("cycle", "report", "nope", cwd=root)
    assert result.returncode != 0
    assert "Cycle not found" in result.stderr
