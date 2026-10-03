"""Work items carry an optional due date; an open item past it reads as overdue."""
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


def test_due_date_is_stored_normalized_and_can_be_cleared(tmp_path):
    root = repo(tmp_path)
    item = json.loads(run("task", "add", "Merge ground", "--due", "2026-10-16", "--json", cwd=root).stdout)
    assert item["due_date"] == "2026-10-16"

    cleared = json.loads(run("task", "set", item["identifier"], "--due", "", "--json", cwd=root).stdout)
    assert cleared["due_date"] is None


def test_a_malformed_due_date_is_refused(tmp_path):
    root = repo(tmp_path)
    bad = run("task", "add", "Nope", "--due", "16.10.2026", cwd=root)
    assert bad.returncode != 0
    assert "YYYY-MM-DD" in bad.stderr + bad.stdout


def test_only_an_open_item_past_its_due_date_is_overdue(tmp_path):
    root = repo(tmp_path)
    late = json.loads(run("task", "add", "Late", "--due", "2020-01-01", "--json", cwd=root).stdout)
    run("task", "add", "Later", "--due", "2999-01-01", cwd=root)

    listing = run("task", "list", cwd=root).stdout
    assert listing.count("OVERDUE") == 1
    assert "OVERDUE" in run("graph", cwd=root).stdout

    run("task", "set", late["identifier"], "--status", "done", cwd=root)
    assert "OVERDUE" not in run("task", "list", cwd=root).stdout


def test_a_database_from_the_branch_flow_release_gains_due_dates(tmp_path):
    db = tmp_path / "nod.db"
    create_schema(db)
    con = sqlite3.connect(db)
    con.execute("ALTER TABLE work_items DROP COLUMN due_date")
    con.execute("PRAGMA user_version = 2")
    con.commit()
    con.close()

    create_session_factory(db)

    con = sqlite3.connect(db)
    assert con.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS) == 3
    assert "due_date" in {row[1] for row in con.execute("PRAGMA table_info(work_items)")}
    con.close()
