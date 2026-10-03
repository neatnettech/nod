from pathlib import Path
from uuid import uuid4
import json
import subprocess

import pytest

from nod.application.services import Services
from nod.domain.models import Project
from nod.infrastructure.database import create_schema, create_session_factory, db_path
from nod.infrastructure.repositories import ProjectRepository
from nod.mcp.server import service


def run(*args, cwd: Path):
    return subprocess.run(["nod", *args], cwd=cwd, text=True, capture_output=True)


def git(*args, cwd: Path):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_worktree_and_subdirectory_share_the_main_checkout_db(tmp_path):
    main, wt = tmp_path / "main", tmp_path / "wt"
    main.mkdir()
    git("init", cwd=main)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "--allow-empty", "-m", "init", cwd=main)
    git("worktree", "add", str(wt), cwd=main)
    sub = main / "sub"
    sub.mkdir()
    db = main / ".nod" / "nod.db"
    assert db_path(wt) == db_path(sub) == db_path(main) == db

    init = run("init", cwd=wt)
    assert init.returncode == 0, init.stderr
    assert str(db) in init.stdout.replace("\n", "")
    assert run("task", "add", "From worktree", cwd=wt).returncode == 0
    assert run("task", "add", "From subdirectory", cwd=sub).returncode == 0
    for cwd in (main, wt, sub):
        board = run("board", "--json", cwd=cwd)
        assert board.returncode == 0, board.stderr
        assert [x["title"] for x in json.loads(board.stdout)["todo"]] == ["From worktree", "From subdirectory"]
    assert db.exists()
    assert not (wt / ".nod").exists()
    assert not (sub / ".nod").exists()


def test_read_before_init_fails_and_creates_nothing(tmp_path, monkeypatch):
    git("init", cwd=tmp_path)
    board = run("board", cwd=tmp_path)
    assert board.returncode != 0
    assert "not initialized" in board.stderr
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="not initialized"):
        service()
    assert not (tmp_path / ".nod").exists()


def test_nod_db_redirects_init_and_reads(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", cwd=repo)
    db = tmp_path / "elsewhere" / "plan.db"
    monkeypatch.setenv("NOD_DB", str(db))
    assert run("init", cwd=repo).returncode == 0
    assert run("task", "add", "Redirected", cwd=repo).returncode == 0
    board = run("board", "--json", cwd=repo)
    assert board.returncode == 0, board.stderr
    assert json.loads(board.stdout)["todo"][0]["title"] == "Redirected"
    assert db.exists()
    assert not (repo / ".nod").exists()


def test_create_task_recovers_from_a_stale_sequence(tmp_path, monkeypatch):
    db = tmp_path / ".nod" / "nod.db"
    create_schema(db)
    session = create_session_factory(db)()
    project = Project(uuid4(), "NOD", "demo")
    ProjectRepository(session).add(project)
    session.commit()
    services = Services(session, project)
    services.create_task("First")

    real = services.items.next_sequence
    calls = []

    def stale_once(project_id):
        calls.append(project_id)
        return 1 if len(calls) == 1 else real(project_id)  # 1 is taken, as if a concurrent writer won the race

    monkeypatch.setattr(services.items, "next_sequence", stale_once)
    assert services.create_task("Second").identifier == "NOD-2"
    assert len(calls) == 2
    assert [x.identifier for x in services.items.list(project.id)] == ["NOD-1", "NOD-2"]
    session.close()
