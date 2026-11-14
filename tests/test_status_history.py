"""Every status change is recorded, so time per stage is known and hold time can be told from work."""
import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from nod.application.services import stage_seconds
from nod.cli.live import make_server
from nod.domain.models import StatusChange
from nod.infrastructure.database import create_session_factory
from test_live import get
from test_llm_pointers import repo, run


def show(root, identifier):
    return json.loads(run("task", "show", identifier, "--json", cwd=root).stdout)


def test_stage_seconds_adds_up_finished_stays_only():
    start = datetime(2026, 10, 10, 9, tzinfo=timezone.utc)
    path = [(None, "todo", 0), ("todo", "in_progress", 1), ("in_progress", "hold", 3), ("hold", "in_progress", 4), ("in_progress", "done", 6)]
    changes = [StatusChange(str(i), "NOD-1", a, b, start + timedelta(hours=h)) for i, (a, b, h) in enumerate(path)]
    assert stage_seconds(changes) == {"todo": 3600, "in_progress": 4 * 3600, "hold": 3600}, "done is still running"
    assert stage_seconds(changes[:1]) == {}


def test_every_move_is_recorded_in_order(tmp_path):
    root = repo(tmp_path)
    run("task", "add", "Tracked", cwd=root)
    for status in ("in_progress", "hold", "in_progress", "done"):
        assert run("task", "set", "NOD-1", "--status", status, cwd=root).returncode == 0
    run("task", "set", "NOD-1", "--status", "done", "--title", "Renamed", cwd=root)  # no move, no entry
    run("task", "set", "NOD-1", "--status", "backlog", cwd=root)  # refused, no entry

    history = show(root, "NOD-1")["history"]
    assert [(c["from"], c["to"]) for c in history] == [
        (None, "todo"), ("todo", "in_progress"), ("in_progress", "hold"), ("hold", "in_progress"), ("in_progress", "done"),
    ]
    assert all(c["at"].endswith("+00:00") for c in history) and [c["at"] for c in history] == sorted(c["at"] for c in history)
    assert history[-1]["at"] == show(root, "NOD-1")["completed_at"], "the log and the stamp share one clock reading"
    assert "Status history" in run("task", "show", "NOD-1", cwd=root).stdout

    from nod.mcp import server
    import os
    here = os.getcwd()
    os.chdir(root)
    try:
        assert len(server.work_item_get("NOD-1")["history"]) == 5
    finally:
        os.chdir(here)


def test_pages_show_history_and_worked_time(tmp_path):
    root = repo(tmp_path)
    run("cycle", "add", "Sprint 1", cwd=root)
    run("task", "add", "Blocked a while", "--cycle", "sprint-1", cwd=root)
    for status in ("in_progress", "hold", "in_progress", "done"):
        run("task", "set", "NOD-1", "--status", status, cwd=root)
    # stretch the recorded moves: 1h of work, 2h on hold, 1h of work
    con = sqlite3.connect(root / ".nod" / "nod.db")
    rows = [r[0] for r in con.execute("SELECT id FROM activity ORDER BY created_at")]
    for row, hour in zip(rows, (8, 9, 10, 12, 13)):
        con.execute("UPDATE activity SET created_at = ? WHERE id = ?", (f"2026-10-10 {hour:02d}:00:00.000000", row))
    con.commit()
    con.close()
    run("task", "set", "NOD-1", "--started-at", "2026-10-10T09:00:00", "--completed-at", "2026-10-10T13:00:00", cwd=root)

    server = make_server(create_session_factory(root / ".nod" / "nod.db"), port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        home = get(server)[1]
        assert "cycle time avg 4h over 1, worked 2h" in home
        assert "13:00:00 UTC · NOD-1 · in progress → done" in home and 'id="feed"' in home
        page = get(server, "/item/NOD-1")[1]
        assert "<dt>Time in progress</dt><dd>2h</dd>" in page and "<dt>Time hold</dt><dd>2h</dd>" in page
        assert "History" in page and "2026-10-10 12:00:00 UTC</b> hold → in progress" in page
    finally:
        server.shutdown()
        server.server_close()
