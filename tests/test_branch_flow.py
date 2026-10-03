"""Work items record where their branch is cut from and where it merges, and an
existing database picks up the new columns in place on its next command."""
from pathlib import Path
import json
import sqlite3
import subprocess

from nod.infrastructure.database import MIGRATIONS, create_schema, create_session_factory


def run(*args, cwd: Path):
    return subprocess.run(["nod", *args], cwd=cwd, text=True, capture_output=True)


def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    assert run("init", cwd=tmp_path).returncode == 0
    return tmp_path


def test_branch_flow_round_trips_through_add_set_list_and_graph(tmp_path):
    root = repo(tmp_path)
    add = run(
        "task", "add", "Clock seam", "--branch", "feat/clock-seam",
        "--from-branch", "chore/ground", "--to-branch", "chore/ground", "--json", cwd=root,
    )
    assert add.returncode == 0, add.stderr
    item = json.loads(add.stdout)
    assert (item["branch_name"], item["from_branch"], item["to_branch"]) == (
        "feat/clock-seam", "chore/ground", "chore/ground",
    )

    # a long lived branch is just an item that merges somewhere else later
    assert run("task", "set", item["identifier"], "--to-branch", "main", cwd=root).returncode == 0
    shown = json.loads(run("task", "show", item["identifier"], "--json", cwd=root).stdout)
    assert (shown["from_branch"], shown["to_branch"]) == ("chore/ground", "main")
    listed = json.loads(run("task", "list", "--json", cwd=root).stdout)
    assert listed[0]["to_branch"] == "main"

    graph = run("graph", cwd=root).stdout.replace("\n", "")
    assert "⎇ feat/clock-seam" in graph and "chore/ground → main" in graph


def test_an_old_database_upgrades_in_place_and_keeps_its_items(tmp_path):
    db = tmp_path / "nod.db"
    create_schema(db)
    # rewind to the schema before branch flow existed, with an item already in it
    con = sqlite3.connect(db)
    t = "2026-01-01 00:00:00"
    con.execute("INSERT INTO projects (id, identifier, name, created_at, updated_at) VALUES ('p', 'OLD', 'old', ?, ?)", (t, t))
    con.execute(
        "INSERT INTO work_items (id, project_id, sequence_id, identifier, title, type, status, priority, "
        "branch_name, created_at, updated_at) "
        "VALUES ('w', 'p', 1, 'OLD-1', 'Kept', 'task', 'todo', 'medium', 'feat/x', ?, ?)", (t, t)
    )
    con.execute("ALTER TABLE work_items DROP COLUMN from_branch")
    con.execute("ALTER TABLE work_items DROP COLUMN to_branch")
    con.execute("PRAGMA user_version = 0")
    con.commit()
    con.close()

    create_session_factory(db)  # any command opens the DB this way
    create_session_factory(db)  # and a second open finds nothing left to do

    con = sqlite3.connect(db)
    assert con.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    columns = {row[1] for row in con.execute("PRAGMA table_info(work_items)")}
    assert {"from_branch", "to_branch"} <= columns
    assert con.execute("SELECT title, branch_name, from_branch FROM work_items").fetchall() == [("Kept", "feat/x", None)]
    con.close()


def test_a_fresh_database_is_stamped_current(tmp_path):
    db = tmp_path / "nod.db"
    create_schema(db)
    con = sqlite3.connect(db)
    assert con.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    con.close()
