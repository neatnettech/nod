"""started_at is stamped on the first move to in progress, so cycle time can be measured."""
import json
import sqlite3
import threading

from nod.cli.live import make_server
from nod.infrastructure.database import MIGRATIONS, create_schema, create_session_factory
from test_live import get
from test_llm_pointers import repo, run


def set_(root, identifier, *args):
    result = run("task", "set", identifier, *args, "--json", cwd=root)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_first_start_is_stamped_and_sticks(tmp_path):
    root = repo(tmp_path)
    item = json.loads(run("task", "add", "Build it", "--json", cwd=root).stdout)
    assert item["started_at"] is None and item["created_at"] is None  # created_at is read back from the database
    ident = item["identifier"]
    listed = json.loads(run("task", "list", "--json", cwd=root).stdout)[0]
    assert listed["created_at"] and listed["started_at"] is None

    started = set_(root, ident, "--status", "in_progress")["started_at"]
    assert started
    assert set_(root, ident, "--status", "hold")["started_at"] == started
    assert set_(root, ident, "--status", "in_progress")["started_at"] == started, "resuming keeps the first start"
    done = set_(root, ident, "--status", "done")
    assert done["started_at"] == started and done["completed_at"]

    born = json.loads(run("task", "add", "Already going", "--status", "in_progress", "--json", cwd=root).stdout)
    assert born["started_at"]


def test_started_at_can_be_backdated_and_cleared(tmp_path):
    root = repo(tmp_path)
    ident = json.loads(run("task", "add", "Backdate me", "--status", "in_progress", "--json", cwd=root).stdout)["identifier"]
    assert set_(root, ident, "--started-at", "2026-10-10T09:00:00")["started_at"].startswith("2026-10-10 09:00")
    assert set_(root, ident, "--started-at", "")["started_at"] is None
    bad = run("task", "set", ident, "--started-at", "yesterday", cwd=root)
    assert bad.returncode != 0 and "Started at must be" in bad.stderr


def test_dashboard_shows_average_cycle_time(tmp_path):
    root = repo(tmp_path)
    run("cycle", "add", "Sprint 1", cwd=root)
    for hours in (2, 4):  # average 3h
        ident = json.loads(run("task", "add", f"Took {hours}h", "--cycle", "sprint-1", "--status", "in_progress", "--json", cwd=root).stdout)["identifier"]
        set_(root, ident, "--status", "done")
        set_(root, ident, "--started-at", "2026-10-10T09:00:00", "--completed-at", f"2026-10-10T{9 + hours}:00:00")
    run("task", "add", "Not done yet", "--cycle", "sprint-1", "--status", "in_progress", cwd=root)

    server = make_server(create_session_factory(root / ".nod" / "nod.db"), port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert "cycle time avg 3h over 2" in get(server)[1]
        page = get(server, "/item/NOD-2")[1]
        assert "<dt>Cycle time</dt><dd>4h</dd>" in page and "<dt>Started</dt>" in page
    finally:
        server.shutdown()
        server.server_close()


def test_a_database_from_before_started_at_gains_the_column(tmp_path):
    db = tmp_path / "nod.db"
    create_schema(db)
    con = sqlite3.connect(db)
    con.execute("ALTER TABLE work_items DROP COLUMN started_at")
    con.execute("PRAGMA user_version = 5")
    con.commit()
    con.close()

    create_session_factory(db)

    con = sqlite3.connect(db)
    assert con.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS) == 6
    assert "started_at" in {row[1] for row in con.execute("PRAGMA table_info(work_items)")}
    con.close()
