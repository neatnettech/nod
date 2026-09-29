from pathlib import Path
import subprocess


def run(*args, cwd: Path):
    return subprocess.run(["nod", *args], cwd=cwd, text=True, capture_output=True)


def test_basic_workflow(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    assert run("init", cwd=tmp_path).returncode == 0
    assert run("module", "add", "Backend", cwd=tmp_path).returncode == 0
    assert run("cycle", "add", "Sprint 1", cwd=tmp_path).returncode == 0
    assert run("task", "add", "Implement authentication", cwd=tmp_path).returncode == 0
    assert run("task", "set", "NOD-1", "--append", "Use JWT.", cwd=tmp_path).returncode == 0
    assert (tmp_path / ".nod" / "nod.db").exists()
