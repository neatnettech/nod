import json
import subprocess
import sys
from pathlib import Path

from test_views import run

SCRIPT = Path(__file__).parent.parent / "scripts" / "sandbox.py"


def sandbox(root, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--dir", str(root), "--no-serve", "--step", "0", *args],
        text=True, capture_output=True,
    )


def test_sandbox_seed_then_scenario(tmp_path):
    root = tmp_path / "box"
    result = sandbox(root, "--seed-only")
    assert result.returncode == 0, result.stderr
    cycles = {c["slug"]: c["status"] for c in json.loads(run("cycle", "list", "--json", cwd=root).stdout)}
    assert cycles == {"sprint-1": "completed", "sprint-2": "active", "sprint-3": "upcoming"}
    items = json.loads(run("task", "list", "--json", cwd=root).stdout)
    assert len(items) == 15 and not [x for x in items if x["status"] == "in_progress"]

    result = sandbox(root)  # reseeds, then plays to the end
    assert result.returncode == 0, result.stderr
    assert "Scenario done." in result.stdout
    cycles = {c["slug"]: c["status"] for c in json.loads(run("cycle", "list", "--json", cwd=root).stdout)}
    assert cycles == {"sprint-1": "completed", "sprint-2": "completed", "sprint-3": "active"}
    sprint_2 = json.loads(run("task", "list", "--cycle", "sprint-2", "--json", cwd=root).stdout)
    assert {x["status"] for x in sprint_2} == {"done"}
    doing = json.loads(run("task", "list", "--status", "in_progress", "--json", cwd=root).stdout)
    assert [x["title"] for x in doing] == ["Order confirmation emails"]


def test_sandbox_refuses_to_wipe_a_foreign_folder(tmp_path):
    (tmp_path / "keep.txt").write_text("mine")
    result = sandbox(tmp_path)
    assert result.returncode != 0 and "refusing to wipe" in result.stderr
    assert (tmp_path / "keep.txt").exists()
