"""Work items point at the plan and memory files an agent wrote for them."""
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


def test_plan_and_memory_paths_are_stored_and_can_be_cleared(tmp_path):
    root = repo(tmp_path)
    item = json.loads(run("task", "add", "Think first", "--plan", "~/.claude/plans/x.md", "--json", cwd=root).stdout)
    assert item["plan_path"] == "~/.claude/plans/x.md"
    assert item["memory_path"] is None

    both = json.loads(run("task", "set", item["identifier"], "--memory", ".claude/memory/nod.md", "--json", cwd=root).stdout)
    assert both["plan_path"] == "~/.claude/plans/x.md", "setting memory leaves the plan alone"
    assert both["memory_path"] == ".claude/memory/nod.md"

    cleared = json.loads(run("task", "set", item["identifier"], "--plan", "", "--memory", "", "--json", cwd=root).stdout)
    assert cleared["plan_path"] is None and cleared["memory_path"] is None


def test_a_database_from_the_due_date_release_gains_agent_paths(tmp_path):
    db = tmp_path / "nod.db"
    create_schema(db)
    con = sqlite3.connect(db)
    con.execute("ALTER TABLE work_items DROP COLUMN plan_path")
    con.execute("ALTER TABLE work_items DROP COLUMN memory_path")
    con.execute("PRAGMA user_version = 3")
    con.commit()
    con.close()

    create_session_factory(db)

    con = sqlite3.connect(db)
    assert con.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS) == 5
    assert {"plan_path", "memory_path"} <= {row[1] for row in con.execute("PRAGMA table_info(work_items)")}
    con.close()
