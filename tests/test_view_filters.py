"""Graph and board can be cut by module or cycle, a filtered graph still names the
prerequisites it does not draw, and an unknown slug is an error, not a silent no-op."""
from pathlib import Path
import json
import subprocess


def run(*args, cwd: Path):
    return subprocess.run(["nod", *args], cwd=cwd, text=True, capture_output=True)


def project(tmp_path: Path) -> Path:
    """NOD-1 (m1, c1)  <-  NOD-2 (m1, c2)  <-  NOD-3 (m2, c1): each depends on the previous."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    for args in (
        ("init",), ("module", "add", "m1"), ("module", "add", "m2"),
        ("cycle", "add", "c1"), ("cycle", "add", "c2"),
        ("task", "add", "Base", "--module", "m1", "--cycle", "c1"),
        ("task", "add", "Middle", "--module", "m1", "--cycle", "c2"),
        ("task", "add", "Top", "--module", "m2", "--cycle", "c1"),
        ("depends", "NOD-2", "NOD-1"), ("depends", "NOD-3", "NOD-2"),
    ):
        result = run(*args, cwd=tmp_path)
        assert result.returncode == 0, (args, result.stderr)
    return tmp_path


def graph_json(root: Path, *args) -> dict:
    data = json.loads(run("graph", *args, "--json", cwd=root).stdout)
    return {n["id"]: n for n in data["nodes"]}, [(e["source"], e["target"]) for e in data["edges"]]


def test_a_cycle_graph_keeps_its_items_and_names_the_blocker_outside(tmp_path):
    root = project(tmp_path)
    nodes, edges = graph_json(root, "--cycle", "c1")
    assert set(nodes) == {"NOD-1", "NOD-3"}
    assert edges == []
    assert nodes["NOD-3"]["needs_outside"] == ["NOD-2"]
    assert nodes["NOD-1"]["needs_outside"] == []
    assert "needs NOD-2 outside this view" in run("graph", "--cycle", "c1", cwd=root).stdout.replace("\n", "")


def test_a_module_graph_keeps_the_dependencies_inside_it(tmp_path):
    root = project(tmp_path)
    nodes, edges = graph_json(root, "--module", "m1")
    assert set(nodes) == {"NOD-1", "NOD-2"}
    assert edges == [("NOD-2", "NOD-1")]
    nodes, _ = graph_json(root, "--module", "m1", "--cycle", "c2")
    assert set(nodes) == {"NOD-2"} and nodes["NOD-2"]["needs_outside"] == ["NOD-1"]


def test_the_board_cuts_by_cycle_and_module(tmp_path):
    root = project(tmp_path)
    board = json.loads(run("board", "--cycle", "c1", "--json", cwd=root).stdout)
    assert [x["identifier"] for x in board["todo"]] == ["NOD-1", "NOD-3"]
    board = json.loads(run("board", "--module", "m2", "--json", cwd=root).stdout)
    assert [x["identifier"] for x in board["todo"]] == ["NOD-3"]


def test_an_unknown_slug_is_an_error_everywhere(tmp_path):
    root = project(tmp_path)
    for args, expected in (
        (("board", "--module", "nope"), "Module not found: nope"),
        (("graph", "--cycle", "nope"), "Cycle not found: nope"),
        (("task", "list", "--module", "nope"), "Module not found: nope"),
        (("task", "add", "Typo", "--cycle", "nope"), "Cycle not found: nope"),
        (("task", "set", "NOD-1", "--module", "nope"), "Module not found: nope"),
    ):
        result = run(*args, cwd=root)
        assert result.returncode != 0, args
        assert expected in (result.stderr + result.stdout).replace("\n", " "), args
    # the typo did not create an unassigned item
    assert len(json.loads(run("task", "list", "--json", cwd=root).stdout)) == 3


def test_items_without_a_module_or_a_cycle_are_orphaned(tmp_path):
    root = project(tmp_path)
    run("task", "add", "Loose", cwd=root)                       # NOD-4: no module, no cycle
    run("task", "add", "Unplanned", "--module", "m1", cwd=root)  # NOD-5: no cycle

    listed = json.loads(run("task", "list", "--orphaned", "--json", cwd=root).stdout)
    assert [x["identifier"] for x in listed] == ["NOD-4", "NOD-5"]
    in_m1 = json.loads(run("task", "list", "--module", "m1", "--orphaned", "--json", cwd=root).stdout)
    assert [x["identifier"] for x in in_m1] == ["NOD-5"]

    board = json.loads(run("board", "--orphaned", "--json", cwd=root).stdout)
    assert [x["identifier"] for x in board["todo"]] == ["NOD-4", "NOD-5"]

    nodes, _ = graph_json(root, "--orphaned")
    assert set(nodes) == {"NOD-4", "NOD-5"}
    assert nodes["NOD-4"]["missing"] == ["module", "cycle"] and nodes["NOD-5"]["missing"] == ["cycle"]

    # the unfiltered views flag them too
    graph = run("graph", cwd=root).stdout.replace("\n", " ")
    assert "ORPHANED: no module, no cycle" in graph and "ORPHANED: no cycle" in graph
    assert run("task", "list", cwd=root).stdout.count("ORPHANED") == 2
