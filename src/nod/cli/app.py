from pathlib import Path
import json
import re

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy.exc import SQLAlchemyError

from nod.application.services import Services
from nod.domain.enums import ModuleStatus, Priority, WorkItemStatus, WorkItemType
from nod.domain.errors import NodError
from nod.infrastructure.database import create_schema, create_session_factory
from nod.infrastructure.repositories import ProjectRepository
from nod.infrastructure.git import GitService

app = typer.Typer(no_args_is_help=True)
module_app = typer.Typer(no_args_is_help=True, help="Manage modules.")
cycle_app = typer.Typer(no_args_is_help=True, help="Manage cycles.")
task_app = typer.Typer(no_args_is_help=True, help="Manage work items.")
app.add_typer(module_app, name="module")
app.add_typer(cycle_app, name="cycle")
app.add_typer(task_app, name="task")

console = Console()

_UNITS = {"h": 1, "m": 1 / 60, "d": 8}


def root() -> Path:
    return Path.cwd()


def require_project():
    factory = create_session_factory(root())
    session = factory()
    try:
        project = ProjectRepository(session).get()
    except SQLAlchemyError:
        session.close()
        raise typer.BadParameter("Nod is not initialized. Run `nod init` first.")
    if not project:
        session.close()
        raise typer.BadParameter("Nod is not initialized. Run `nod init` first.")
    return session, project


def output(value, as_json: bool):
    if as_json:
        if hasattr(value, "__dict__"):
            data = {k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v for k, v in value.__dict__.items()}
        else:
            data = value
        typer.echo(json.dumps(data, default=str, indent=2))
    else:
        console.print(value)


def _parse_hours(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*([hmd]?)", value.strip())
    if not match:
        raise typer.BadParameter(f"Invalid estimate: {value}")
    return float(match.group(1)) * _UNITS[match.group(2) or "h"]


@app.command()
def init(identifier: str = typer.Option("NOD", "--identifier"), name: str = typer.Option(None, "--name")):
    """Initialize Nod in the current Git repository."""
    r = root()
    git = GitService(r)
    if not git.is_repository():
        raise typer.BadParameter("Current directory is not a Git repository.")
    create_schema(r)
    factory = create_session_factory(r)
    session = factory()
    if not ProjectRepository(session).get():
        from nod.domain.models import Project
        from uuid import uuid4
        project = Project(uuid4(), identifier.upper(), name or r.name)
        ProjectRepository(session).add(project)
        session.commit()
    session.close()
    console.print("[green]Initialized Nod[/green] in .nod/")


@app.command("depends")
def depends(source: str, target: str):
    """Record that a work item depends on another."""
    session, project = require_project()
    try:
        Services(session, project).add_dependency(source, target)
        console.print(f"[green]{source} depends on {target}[/green]")
    except NodError as exc:
        raise typer.BadParameter(str(exc))
    finally:
        session.close()


STATUS_GLYPHS = {
    "backlog": "· BACKLOG",
    "todo": "○ TODO",
    "in_progress": "◐ IN_PROGRESS",
    "done": "✓ DONE",
    "cancelled": "✗ CANCELLED",
}


def render_dependency_tree(graph) -> list[str]:
    """ASCII tree of prerequisites. Arrow points to the dependent item."""
    children: dict = {}
    for u, v, data in graph.edges(data=True):
        relation = data.get("relation")
        if relation == "depends_on":
            children.setdefault(v, []).append((u, relation))
        elif relation == "blocks":
            children.setdefault(u, []).append((v, relation))

    needy = {
        u for u, v, d in graph.edges(data=True) if d.get("relation") == "depends_on"
    } | {
        v for u, v, d in graph.edges(data=True) if d.get("relation") == "blocks"
    }
    roots = sorted(n for n in graph.nodes if n not in needy)

    lines: list[str] = []
    seen: set = set()

    def node_text(n: str) -> str:
        attrs = dict(graph.nodes[n])
        text = f"{n}  {attrs.get('title', '')}".rstrip()
        status = attrs.get("status")
        if status:
            text += f"  {STATUS_GLYPHS.get(status, status)}"
        branch = attrs.get("branch")
        if branch:
            text += f"  ⎇ {branch}"
        return text

    def draw_children(node: str, prefix: str) -> None:
        kids = sorted(children.get(node, []), key=lambda pair: pair[0])
        for i, (child, relation) in enumerate(kids):
            last = i == len(kids) - 1
            connector = "└─► " if last else "├─► "
            if child in seen:
                lines.append(prefix + connector + f"{node_text(child)}  (see above)")
                continue
            seen.add(child)
            suffix = "  (depends on this)" if relation == "depends_on" else "  (blocked by this)"
            lines.append(prefix + connector + node_text(child) + suffix)
            draw_children(child, prefix + ("   " if last else "│  "))

    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        lines.append(node_text(root))
        draw_children(root, "")
    return lines


@app.command()
def graph(as_json: bool = typer.Option(False, "--json")):
    """Graph of work item dependencies."""
    session, project = require_project()
    try:
        g = Services(session, project).graph()
        if as_json:
            data = {
                "nodes": [{"id": n, **attrs} for n, attrs in g.nodes(data=True)],
                "edges": [{"source": s, "target": t, **attrs} for s, t, attrs in g.edges(data=True)],
            }
            typer.echo(json.dumps(data, indent=2, default=str))
            return
        if not g.nodes:
            console.print("No work items.")
            return
        for line in render_dependency_tree(g):
            console.print(line)
    finally:
        session.close()


@app.command()
def board(
    module: str = typer.Option(None, "--module"),
    cycle: str = typer.Option(None, "--cycle"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Kanban board of work items grouped by status."""
    session, project = require_project()
    try:
        services = Services(session, project)
        module_obj = services.modules.get(module) if module else None
        cycle_obj = services.cycles.get(cycle) if cycle else None
        items = services.items.list(project.id, module=module_obj, cycle=cycle_obj)
        if as_json:
            data = {
                status.value: [
                    {"identifier": x.identifier, "title": x.title, "priority": x.priority.value, "estimate": x.estimate}
                    for x in items if x.status == status
                ]
                for status in WorkItemStatus
            }
            typer.echo(json.dumps(data, indent=2))
            return
        columns = {status: [] for status in WorkItemStatus}
        for x in items:
            columns[x.status].append(f"{x.identifier}  {x.title}")
        table = Table(show_header=True, header_style="bold", expand=True)
        for status in WorkItemStatus:
            table.add_column(status.value.upper(), overflow="fold")
        height = max(len(v) for v in columns.values()) or 1
        for i in range(height):
            table.add_row(*(columns[status][i] if i < len(columns[status]) else "" for status in WorkItemStatus))
        console.print(table)
    finally:
        session.close()


@app.command()
def timeline(as_json: bool = typer.Option(False, "--json")):
    """Cycles over time with per-cycle totals."""
    session, project = require_project()
    try:
        services = Services(session, project)
        cycles = sorted(services.cycles.list(), key=lambda c: (c.start_date or "9999", c.end_date or "9999"))
        rows = []
        for c in cycles:
            items = services.items.list(project.id, cycle=c)
            total = sum(i.estimate or 0 for i in items)
            rows.append({
                "slug": c.slug, "name": c.name, "status": c.status.value,
                "start": c.start_date, "end": c.end_date,
                "items": len(items), "estimate_h": round(total, 1),
            })
        if as_json:
            typer.echo(json.dumps(rows, indent=2))
            return
        if not rows:
            console.print("No cycles.")
            return
        dated = [r for r in rows if r["start"] and r["end"]]
        if dated:
            from datetime import date
            t0 = min(date.fromisoformat(r["start"]) for r in dated)
            t1 = max(date.fromisoformat(r["end"]) for r in dated)
            span = max((t1 - t0).days, 1)
            table = Table("Cycle", "Dates", "Timeline", "Items", "Estimate")
            for r in rows:
                if r["start"] and r["end"]:
                    offset = (date.fromisoformat(r["start"]) - t0).days
                    length = max((date.fromisoformat(r["end"]) - date.fromisoformat(r["start"])).days, 1)
                    bar = " " * max(offset, 0) + "█" * max(round(length / span * 30), 1)
                else:
                    bar = "[dim]no dates[/dim]"
                table.add_row(r["name"], f"{r['start'] or ''} → {r['end'] or ''}", bar, str(r["items"]), f"{r['estimate_h']}h")
            console.print(table)
            return
        table = Table("Cycle", "Status", "Items", "Estimate")
        for r in rows:
            table.add_row(r["name"], r["status"], str(r["items"]), f"{r['estimate_h']}h")
        console.print(table)
        console.print("[dim]Set cycle --start/--end dates to get a chronological timeline.[/dim]")
    finally:
        session.close()


@module_app.command("add")
def module_add(
    name: str = typer.Argument(...),
    description: str = typer.Option(None, "--description"),
    as_json: bool = typer.Option(False, "--json"),
):
    session, project = require_project()
    try:
        result = Services(session, project).create_module(name, description=description)
        output(result, as_json)
    except NodError as exc:
        raise typer.BadParameter(str(exc))
    finally:
        session.close()


@module_app.command("set")
def module_set(
    ref: str = typer.Argument(...),
    title: str = typer.Option(None, "--title"),
    description: str = typer.Option(None, "--description"),
    append: str = typer.Option(None, "--append"),
    status: str = typer.Option(None, "--status"),
    as_json: bool = typer.Option(False, "--json"),
):
    session, project = require_project()
    try:
        result = Services(session, project).update_module(ref, title=title, description=description, append=append, status=status)
        output(result, as_json)
    except NodError as exc:
        raise typer.BadParameter(str(exc))
    finally:
        session.close()


@module_app.command("show")
def module_show(ref: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")):
    session, project = require_project()
    try:
        services = Services(session, project)
        result = services.modules.get(ref)
        if not result:
            raise typer.BadParameter(f"Module not found: {ref}")
        output(result, as_json)
    finally:
        session.close()


@module_app.command("list")
def module_list(as_json: bool = typer.Option(False, "--json")):
    session, project = require_project()
    try:
        services = Services(session, project)
        rows = services.modules.list()
        if as_json:
            typer.echo(json.dumps([vars(x) for x in rows], default=str, indent=2))
            return
        table = Table("Slug", "Name", "Status")
        for x in rows:
            table.add_row(x.slug, x.name, x.status.value)
        console.print(table)
    finally:
        session.close()


@cycle_app.command("add")
def cycle_add(
    name: str = typer.Argument(...),
    description: str = typer.Option(None, "--description"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    as_json: bool = typer.Option(False, "--json"),
):
    session, project = require_project()
    try:
        result = Services(session, project).create_cycle(name, start=start, end=end, description=description)
        output(result, as_json)
    except NodError as exc:
        raise typer.BadParameter(str(exc))
    finally:
        session.close()


@cycle_app.command("set")
def cycle_set(
    ref: str = typer.Argument(...),
    title: str = typer.Option(None, "--title"),
    description: str = typer.Option(None, "--description"),
    append: str = typer.Option(None, "--append"),
    status: str = typer.Option(None, "--status"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    as_json: bool = typer.Option(False, "--json"),
):
    session, project = require_project()
    try:
        result = Services(session, project).update_cycle(
            ref, title=title, description=description, append=append,
            status=status, start=start, end=end,
        )
        output(result, as_json)
    except NodError as exc:
        raise typer.BadParameter(str(exc))
    finally:
        session.close()


@cycle_app.command("show")
def cycle_show(ref: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")):
    session, project = require_project()
    try:
        services = Services(session, project)
        result = services.cycles.get(ref)
        if not result:
            raise typer.BadParameter(f"Cycle not found: {ref}")
        output(result, as_json)
    finally:
        session.close()


@cycle_app.command("list")
def cycle_list(as_json: bool = typer.Option(False, "--json")):
    session, project = require_project()
    try:
        services = Services(session, project)
        rows = services.cycles.list()
        if as_json:
            typer.echo(json.dumps([vars(x) for x in rows], default=str, indent=2))
            return
        table = Table("Slug", "Name", "Status", "Start", "End")
        for x in rows:
            table.add_row(x.slug, x.name, x.status.value, x.start_date or "", x.end_date or "")
        console.print(table)
    finally:
        session.close()


@task_app.command("add")
def task_add(
    title: str = typer.Argument(...),
    description: str = typer.Option(None, "--description"),
    type_: str = typer.Option("task", "--type"),
    priority: str = typer.Option("medium", "--priority"),
    status: str = typer.Option(None, "--status"),
    module: str = typer.Option(None, "--module"),
    cycle: str = typer.Option(None, "--cycle"),
    estimate: str = typer.Option(None, "--estimate"),
    branch: str = typer.Option(None, "--branch"),
    as_json: bool = typer.Option(False, "--json"),
):
    session, project = require_project()
    try:
        services = Services(session, project)
        module_obj = services.modules.get(module) if module else None
        cycle_obj = services.cycles.get(cycle) if cycle else None
        result = services.create_task(
            title, description=description, type_=WorkItemType(type_),
            priority=Priority(priority), module=module_obj, cycle=cycle_obj,
            estimate=_parse_hours(estimate),
            status=WorkItemStatus(status) if status else None,
            branch=branch,
        )
        output(result, as_json)
    except NodError as exc:
        raise typer.BadParameter(str(exc))
    finally:
        session.close()


@task_app.command("set")
def task_set(
    identifier: str = typer.Argument(...),
    title: str = typer.Option(None, "--title"),
    description: str = typer.Option(None, "--description"),
    append: str = typer.Option(None, "--append"),
    status: str = typer.Option(None, "--status"),
    priority: str = typer.Option(None, "--priority"),
    module: str = typer.Option(None, "--module"),
    cycle: str = typer.Option(None, "--cycle"),
    estimate: str = typer.Option(None, "--estimate"),
    branch: str = typer.Option(None, "--branch"),
    as_json: bool = typer.Option(False, "--json"),
):
    session, project = require_project()
    try:
        services = Services(session, project)
        module_obj = services.modules.get(module) if module else None
        cycle_obj = services.cycles.get(cycle) if cycle else None
        result = services.update_task(
            identifier, title=title, description=description, append=append,
            status=status, priority=priority, module=module_obj, cycle=cycle_obj,
            branch=branch, estimate=_parse_hours(estimate),
        )
        output(result, as_json)
    except NodError as exc:
        raise typer.BadParameter(str(exc))
    finally:
        session.close()


@task_app.command("show")
def task_show(identifier: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")):
    session, project = require_project()
    try:
        services = Services(session, project)
        result = services.items.get(project.id, identifier)
        if not result:
            raise typer.BadParameter(f"Work item not found: {identifier}")
        output(result, as_json)
    finally:
        session.close()


@task_app.command("list")
def task_list(
    status: str = typer.Option(None, "--status"),
    module: str = typer.Option(None, "--module"),
    cycle: str = typer.Option(None, "--cycle"),
    priority: str = typer.Option(None, "--priority"),
    type_: str = typer.Option(None, "--type"),
    as_json: bool = typer.Option(False, "--json"),
):
    session, project = require_project()
    try:
        services = Services(session, project)
        module_obj = services.modules.get(module) if module else None
        cycle_obj = services.cycles.get(cycle) if cycle else None
        rows = services.items.list(
            project.id,
            status=WorkItemStatus(status) if status else None,
            module=module_obj,
            cycle=cycle_obj,
            priority=Priority(priority) if priority else None,
            type_=WorkItemType(type_) if type_ else None,
        )
        if as_json:
            typer.echo(json.dumps([vars(x) for x in rows], default=str, indent=2))
            return
        table = Table("ID", "Title", "Module", "Estimate", "Status", "Priority", "Branch")
        modules = {m.id: m.slug for m in services.modules.list()}
        for x in rows:
            table.add_row(
                x.identifier, x.title, modules.get(x.module_id) or "",
                f"{x.estimate:g}h" if x.estimate else "",
                x.status.value, x.priority.value, x.branch_name or "",
            )
        console.print(table)
    finally:
        session.close()
