"""An item can sit under an epic: the parent must be an epic, never itself, never a loop;
closing the parent leaves its children alone."""
from pathlib import Path
import json
import subprocess


def run(*args, cwd: Path):
    return subprocess.run(["nod", *args], cwd=cwd, text=True, capture_output=True)


def project(tmp_path: Path) -> Path:
    """NOD-1 epic, NOD-2 epic, NOD-3 task, NOD-4 task."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    for args in (
        ("init",),
        ("task", "add", "Big", "--type", "epic"),
        ("task", "add", "Other", "--type", "epic"),
        ("task", "add", "Slice one"),
        ("task", "add", "Slice two"),
    ):
        result = run(*args, cwd=tmp_path)
        assert result.returncode == 0, (args, result.stderr)
    return tmp_path


def show(root, ident):
    return json.loads(run("task", "show", ident, "--json", cwd=root).stdout)


def test_add_and_set_attach_and_no_parent_detaches(tmp_path):
    root = project(tmp_path)
    assert run("task", "add", "New", "--parent", "NOD-1", cwd=root).returncode == 0
    assert show(root, "NOD-5")["parent"] == "NOD-1"
    assert run("task", "set", "NOD-3", "--parent", "nod-1", cwd=root).returncode == 0
    assert show(root, "NOD-3")["parent"] == "NOD-1"
    assert run("task", "set", "NOD-3", "--no-parent", cwd=root).returncode == 0
    assert show(root, "NOD-3")["parent"] is None
    assert run("task", "set", "NOD-3", "--parent", "NOD-1", "--no-parent", cwd=root).returncode != 0


def test_parent_must_exist_and_be_an_epic(tmp_path):
    root = project(tmp_path)
    assert "not an epic" in run("task", "set", "NOD-3", "--parent", "NOD-4", cwd=root).stderr.replace("\n", " ")
    assert "Parent not found" in run("task", "set", "NOD-3", "--parent", "NOD-99", cwd=root).stderr.replace("\n", " ")
    assert run("task", "add", "X", "--parent", "NOD-4", cwd=root).returncode != 0


def test_no_self_parent_and_no_loop(tmp_path):
    root = project(tmp_path)
    assert run("task", "set", "NOD-1", "--parent", "NOD-1", cwd=root).returncode != 0
    assert run("task", "set", "NOD-1", "--parent", "NOD-2", cwd=root).returncode == 0
    loop = run("task", "set", "NOD-2", "--parent", "NOD-1", cwd=root)
    assert loop.returncode != 0 and "ancestor" in loop.stderr.replace("\n", " ")


def test_list_filter_and_show_children(tmp_path):
    root = project(tmp_path)
    for n in ("NOD-3", "NOD-4"):
        run("task", "set", n, "--parent", "NOD-1", cwd=root)
    rows = json.loads(run("task", "list", "--parent", "NOD-1", "--json", cwd=root).stdout)
    assert [r["identifier"] for r in rows] == ["NOD-3", "NOD-4"]
    assert [c["identifier"] for c in show(root, "NOD-1")["children"]] == ["NOD-3", "NOD-4"]
    assert "NOD-3" in run("task", "show", "NOD-1", cwd=root).stdout
    assert run("task", "list", "--parent", "NOD-99", cwd=root).returncode != 0


def test_closing_the_parent_leaves_children_attached(tmp_path):
    root = project(tmp_path)
    run("task", "set", "NOD-3", "--parent", "NOD-1", cwd=root)
    assert run("task", "set", "NOD-1", "--status", "done", cwd=root).returncode == 0
    child = show(root, "NOD-3")
    assert child["parent"] == "NOD-1" and child["status"] == "todo"


def test_mcp_tools_take_and_return_parent(tmp_path, monkeypatch):
    root = project(tmp_path)
    monkeypatch.chdir(root)
    from nod.mcp import server
    made = server.work_item_create("Via mcp", parent="NOD-1")
    assert server.work_item_get("NOD-1")["children"][0]["identifier"] == made["identifier"]
    assert [x["identifier"] for x in server.work_item_list(parent="NOD-1")] == [made["identifier"]]
    server.work_item_update(made["identifier"], parent="")
    assert server.work_item_get(made["identifier"])["parent"] is None
