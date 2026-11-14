"""Work items move through their stages in order, and the timestamps follow the moves."""
import json

import pytest

from nod.domain.enums import TRANSITIONS, WorkItemStatus
from test_llm_pointers import repo, run


def add(root, title, *args):
    return json.loads(run("task", "add", title, *args, "--json", cwd=root).stdout)["identifier"]


def move(root, identifier, status):
    return run("task", "set", identifier, "--status", status, "--json", cwd=root)


def test_every_status_has_a_way_on_and_names_only_real_statuses():
    assert set(TRANSITIONS) == set(WorkItemStatus)
    assert all(targets and source not in targets for source, targets in TRANSITIONS.items())


def test_stages_cannot_be_skipped(tmp_path):
    root = repo(tmp_path)
    ident = add(root, "Step by step", "--status", "backlog")
    for skipped in ("in_progress", "hold", "done"):
        refused = move(root, ident, skipped)
        assert refused.returncode != 0
        assert f"cannot go from backlog to {skipped}" in refused.stderr
    assert "backlog, in_progress, cancelled." in move(root, add(root, "Todo"), "done").stderr, "the refusal names what is allowed"

    for status in ("todo", "in_progress", "hold", "in_progress", "done"):
        assert move(root, ident, status).returncode == 0, status
    assert move(root, ident, "hold").returncode != 0, "a done item is reopened, not blocked"
    assert move(root, ident, "cancelled").returncode != 0
    assert move(root, ident, "done").returncode == 0, "the same status is a no op"
    assert "Unknown status" in move(root, ident, "finished").stderr


def test_a_new_item_cannot_be_born_finished(tmp_path):
    root = repo(tmp_path)
    for status in ("done", "hold", "cancelled"):
        refused = run("task", "add", "Shortcut", "--status", status, cwd=root)
        assert refused.returncode != 0 and "cannot start as" in refused.stderr
    assert json.loads(run("task", "list", "--json", cwd=root).stdout) == []


def test_timestamps_follow_the_moves(tmp_path):
    root = repo(tmp_path)
    ident = add(root, "Clocked")
    started = json.loads(move(root, ident, "in_progress").stdout)["started_at"]
    assert started.endswith("+00:00"), "times are UTC"

    back = json.loads(move(root, ident, "todo").stdout)
    assert back["started_at"] is None, "handed back means not started"
    move(root, ident, "in_progress")
    done = json.loads(move(root, ident, "done").stdout)
    assert done["started_at"] and done["completed_at"].endswith("+00:00")

    reopened = json.loads(move(root, ident, "in_progress").stdout)
    assert reopened["completed_at"] is None and reopened["started_at"] == done["started_at"]
    cancelled = json.loads(move(root, ident, "cancelled").stdout)
    assert cancelled["started_at"] == done["started_at"] and cancelled["completed_at"] is None


def test_hand_set_stamps_must_fit_the_stage(tmp_path):
    root = repo(tmp_path)
    ident = add(root, "Honest")

    def stamp(*args):
        return run("task", "set", ident, *args, cwd=root)

    assert "has not started" in stamp("--started-at", "2026-10-10T09:00:00").stderr
    assert "only a done item" in stamp("--completed-at", "2026-10-10T09:00:00").stderr
    move(root, ident, "in_progress")
    assert "only a done item" in stamp("--completed-at", "2026-10-10T09:00:00").stderr
    move(root, ident, "done")
    early = stamp("--started-at", "2026-10-10T09:00:00", "--completed-at", "2026-10-09T09:00:00")
    assert early.returncode != 0 and "cannot be before" in early.stderr
    assert stamp("--started-at", "2026-10-10T09:00:00", "--completed-at", "2026-10-10T12:00:00+02:00").returncode == 0
    shown = json.loads(run("task", "show", ident, "--json", cwd=root).stdout)
    assert shown["completed_at"].startswith("2026-10-10 10:00:00"), "another zone is stored as UTC"


def test_mcp_refuses_a_skipped_stage(tmp_path, monkeypatch):
    root = repo(tmp_path)
    monkeypatch.chdir(root)
    from nod.domain.errors import ValidationError
    from nod.mcp import server
    made = server.work_item_create("Via mcp", status="in_progress")
    assert made["started_at"]
    with pytest.raises(ValidationError, match="cannot go from in_progress to backlog"):
        server.work_item_update(made["identifier"], status="backlog")
    with pytest.raises(ValidationError, match="cannot start as done"):
        server.work_item_create("Shortcut", status="done")
