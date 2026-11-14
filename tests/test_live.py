import threading
import urllib.error
import urllib.request

from nod.cli.live import make_server
from nod.infrastructure.database import create_session_factory
from test_views import run, setup


def get(server, path="/"):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}{path}") as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def test_live_dashboard_follows_changes(tmp_path):
    root = setup(tmp_path)
    server = make_server(create_session_factory(root / ".nod" / "nod.db"), port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        status, page = get(server)  # empty project still renders
        assert status == 200 and "No cycles yet" in page and "Nothing in progress" in page

        run("module", "add", "Vault", cwd=root)
        run("task", "add", "Loose end", "--module", "vault", cwd=root)
        run("cycle", "add", "Sprint 1", cwd=root)
        run("cycle", "add", "Sprint 2", cwd=root)
        run("cycle", "set", "sprint-1", "--status", "active", cwd=root)
        run("task", "add", "<script>alert(1)</script>", "--module", "vault", "--cycle", "sprint-1", cwd=root)
        run("task", "add", "Later", "--module", "vault", "--cycle", "sprint-2", "--status", "in_progress", cwd=root)
        run("task", "set", "NOD-3", "--status", "done", cwd=root)

        before = get(server)[1]
        # every cycle is listed, the active one is current, unplaced items get their own row
        assert 'href="/cycle/sprint-1"' in before and 'href="/cycle/sprint-2"' in before
        assert before.count(">current<") == 1 and 'href="/unplanned"' in before
        assert "100% · 1/1 done · 0 doing" in before
        assert all(x in before for x in ("NOD-1", "NOD-2", "NOD-3"))
        assert "&lt;script&gt;alert" in before and "<script>alert" not in before

        assert run("task", "set", "NOD-2", "--status", "in_progress", "--branch", "feat/x", cwd=root).returncode == 0
        after = get(server)[1]
        assert after != before  # what the page script reloads on
        assert "Nothing in progress" not in after and "0% · 0/1 done · 1 doing" in after
        # the Now card and the cycle column, each with its own transition name
        assert after.count('data-id="NOD-2" data-status="in_progress"') == 2
        assert "view-transition-name:n2" in after and "view-transition-name:l2" in after

        status, page = get(server, "/cycle/sprint-1")
        assert status == 200 and "NOD-2" in page and "NOD-1" not in page and 'href="/"' in page
        status, page = get(server, "/unplanned")
        assert status == 200 and "NOD-1" in page and "NOD-2" not in page
        assert get(server, "/cycle/nope")[0] == 404

        # every item links to its own page: facts, description, epic, children, dependencies
        assert after.count('class="item-link" href="/item/NOD-2"') == 2
        assert "· NOD-2 · todo → in progress</a>" in after, "the feed is the recorded history"
        run("task", "add", "Epic", "--type", "epic", "--description", "Line one\n<b>two</b>", cwd=root)
        run("task", "set", "NOD-1", "--parent", "NOD-4", cwd=root)
        run("depends", "NOD-1", "NOD-2", cwd=root)
        status, page = get(server, "/item/NOD-1")
        assert status == 200 and "Loose end" in page and "Vault" in page
        assert "Needs first" in page and 'href="/item/NOD-2"' in page and 'href="/item/NOD-4"' in page
        assert "Unblocks" in get(server, "/item/NOD-2")[1]
        epic = get(server, "/item/NOD-4")[1]
        assert "Children" in epic and 'href="/item/NOD-1"' in epic and "&lt;b&gt;two&lt;/b&gt;" in epic
        assert get(server, "/item/NOD-99")[0] == 404
        assert get(server, "/nope")[0] == 404
    finally:
        server.shutdown()
        server.server_close()
