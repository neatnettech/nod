from pathlib import Path
import json
import subprocess


def run(*args, cwd: Path):
    return subprocess.run(["nod", *args], cwd=cwd, text=True, capture_output=True)


def setup(tmp_path: Path) -> Path:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    assert run("init", cwd=tmp_path).returncode == 0
    return tmp_path


def test_task_creation_with_description_and_estimate(tmp_path):
    root = setup(tmp_path)
    assert run("module", "add", "Vault", cwd=root).returncode == 0
    assert run("cycle", "add", "Sprint 1", "--start", "2026-10-01", "--end", "2026-10-14", cwd=root).returncode == 0
    result = run(
        "task", "add", "StateBadge component",
        "--module", "vault", "--cycle", "sprint-1",
        "--estimate", "2h",
        "--description", "Three states with icon and word, never color alone.",
        "--json", cwd=root,
    )
    assert result.returncode == 0, result.stderr
    item = json.loads(result.stdout)
    assert item["estimate"] == 2.0
    assert item["description"].startswith("Three states")
    assert item["module_id"] is not None
    assert item["cycle_id"] is not None


def test_board_and_timeline(tmp_path):
    root = setup(tmp_path)
    run("module", "add", "Vault", cwd=root)
    run("cycle", "add", "Sprint 1", "--start", "2026-10-01", "--end", "2026-10-14", cwd=root)
    run("task", "add", "Note editor", "--module", "vault", "--cycle", "sprint-1", "--estimate", "4h", cwd=root)
    run("task", "add", "Category management", "--module", "vault", "--cycle", "sprint-1", "--estimate", "3h", "--status", "in_progress", cwd=root)

    board = run("board", "--json", cwd=root)
    assert board.returncode == 0, board.stderr
    data = json.loads(board.stdout)
    assert data["todo"][0]["title"] == "Note editor"
    assert data["in_progress"][0]["title"] == "Category management"

    timeline = run("timeline", "--json", cwd=root)
    assert timeline.returncode == 0, timeline.stderr
    rows = json.loads(timeline.stdout)
    assert rows[0]["name"] == "Sprint 1"
    assert rows[0]["items"] == 2
    assert rows[0]["estimate_h"] == 7.0

    plain = run("board", cwd=root)
    assert plain.returncode == 0


def test_dependency_graph(tmp_path):
    root = setup(tmp_path)
    run("task", "add", "First", cwd=root)
    run("task", "add", "Second", cwd=root)
    run("task", "add", "Third", cwd=root)
    assert run("task", "set", "NOD-1", "--status", "done", "--branch", "feat/first", cwd=root).returncode == 0
    assert run("depends", "NOD-2", "NOD-1", cwd=root).returncode == 0
    assert run("depends", "NOD-3", "NOD-1", cwd=root).returncode == 0
    graph = run("graph", "--json", cwd=root)
    assert graph.returncode == 0, graph.stderr
    data = json.loads(graph.stdout)
    assert any(e["source"] == "NOD-2" and e["target"] == "NOD-1" for e in data["edges"])

    plain = run("graph", cwd=root)
    assert plain.returncode == 0, plain.stderr
    assert "└─►" in plain.stdout
    assert "(depends on this)" in plain.stdout
    assert "✓ DONE" in plain.stdout
    assert "⎇ feat/first" in plain.stdout
    assert plain.stdout.index("NOD-1") < plain.stdout.index("NOD-2") < plain.stdout.index("NOD-3")
