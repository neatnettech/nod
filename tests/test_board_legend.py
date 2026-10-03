"""The board says where each item belongs: module colour, cycle letter, and a legend
for what is on screen. Stored titles are data, never Rich markup."""
from pathlib import Path
import json
import os
import subprocess


def run(*args, cwd: Path, colour: bool = False):
    env = {**os.environ, "COLUMNS": "160"}
    env.pop("NO_COLOR", None)
    if colour:
        env["FORCE_COLOR"] = "1"
    return subprocess.run(["nod", *args], cwd=cwd, text=True, capture_output=True, env=env)


def project(tmp_path: Path) -> Path:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    for args in (
        ("init",), ("module", "add", "m1"), ("module", "add", "m2"),
        ("cycle", "add", "c1", "--start", "2026-10-01"),
        ("cycle", "add", "c2", "--start", "2026-09-01", "--end", "2026-09-30"),
        ("task", "add", "Alpha", "--module", "m1", "--cycle", "c1"),
        ("task", "add", "Beta", "--module", "m2", "--cycle", "c2"),
        ("task", "add", "[Epic] Loose"),
    ):
        assert run(*args, cwd=tmp_path).returncode == 0, args
    return tmp_path


def test_items_carry_a_cycle_letter_and_the_legend_explains_them(tmp_path):
    out = run("board", cwd=project(tmp_path)).stdout
    # cycles are lettered in date order: c2 starts first
    assert "NOD-1  Alpha  [B]" in out and "NOD-2  Beta  [A]" in out
    assert "NOD-3  [Epic] Loose  [orphaned]" in out
    assert "Modules: ■ m1   ■ m2" in out
    assert "Cycles:  [A] c2 (2026-09-01 → 2026-09-30)   [B] c1 (2026-10-01 → ?)" in out


def test_a_module_colour_on_the_board_matches_its_legend_square(tmp_path):
    out = run("board", cwd=project(tmp_path), colour=True).stdout
    assert "\x1b[1;36mNOD-1" in out and "\x1b[36m■" in out  # m1 is the first palette colour
    assert "\x1b[1;35mNOD-2" in out and "\x1b[35m■" in out  # m2 the second


def test_the_legend_lists_only_what_is_on_the_board(tmp_path):
    out = run("board", "--module", "m1", cwd=project(tmp_path)).stdout
    assert "Modules: ■ m1" in out and "m2" not in out.split("Modules:")[1].split("\n")[0]
    assert "Cycles:  [B] c1" in out and "c2" not in out.split("Cycles:")[1]


def test_board_json_names_module_and_cycle(tmp_path):
    board = json.loads(run("board", "--json", cwd=project(tmp_path)).stdout)
    assert [(x["identifier"], x["module"], x["cycle"]) for x in board["todo"]] == [
        ("NOD-1", "m1", "c1"), ("NOD-2", "m2", "c2"), ("NOD-3", None, None),
    ]


def test_bracketed_titles_print_literally_in_list_and_graph(tmp_path):
    root = project(tmp_path)
    assert "[Epic] Loose" in run("task", "list", cwd=root).stdout
    assert "[Epic] Loose" in run("graph", cwd=root).stdout
