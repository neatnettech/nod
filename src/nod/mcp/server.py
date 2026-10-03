from mcp.server.fastmcp import FastMCP
from sqlalchemy.exc import SQLAlchemyError

from nod.infrastructure.database import create_session_factory, db_path
from nod.infrastructure.repositories import ProjectRepository
from nod.application.services import Services

mcp = FastMCP("nod")


def service():
    db = db_path()
    if not db.exists():
        raise RuntimeError("Nod is not initialized in this repository.")
    session = create_session_factory(db)()
    try:
        project = ProjectRepository(session).get()
    except SQLAlchemyError:
        session.close()
        raise RuntimeError("Nod is not initialized in this repository.")
    if not project:
        session.close()
        raise RuntimeError("Nod is not initialized in this repository.")
    return session, Services(session, project)


@mcp.tool()
def project_get() -> dict:
    session, svc = service()
    try:
        return {
            "id": str(svc.project.id),
            "identifier": svc.project.identifier,
            "name": svc.project.name,
            "description": svc.project.description,
        }
    finally:
        session.close()


@mcp.tool()
def work_item_list(
    status: str | None = None,
    module: str | None = None,
    cycle: str | None = None,
) -> list[dict]:
    from nod.domain.enums import WorkItemStatus
    session, svc = service()
    try:
        module_obj = svc.modules.get(module) if module else None
        cycle_obj = svc.cycles.get(cycle) if cycle else None
        rows = svc.items.list(
            svc.project.id,
            status=WorkItemStatus(status) if status else None,
            module=module_obj,
            cycle=cycle_obj,
        )
        return [vars(x) for x in rows]
    finally:
        session.close()


@mcp.tool()
def work_item_get(identifier: str) -> dict:
    session, svc = service()
    try:
        item = svc.items.get(svc.project.id, identifier)
        if not item:
            raise ValueError(f"Work Item not found: {identifier}")
        return vars(item)
    finally:
        session.close()


@mcp.tool()
def work_item_create(
    title: str,
    type: str = "task",
    priority: str = "medium",
    description: str | None = None,
    module: str | None = None,
    cycle: str | None = None,
    estimate: float | None = None,
    branch: str | None = None,
    from_branch: str | None = None,
    to_branch: str | None = None,
) -> dict:
    from nod.domain.enums import WorkItemType, Priority
    session, svc = service()
    try:
        module_obj = svc.modules.get(module) if module else None
        cycle_obj = svc.cycles.get(cycle) if cycle else None
        item = svc.create_task(
            title, description=description, type_=WorkItemType(type),
            priority=Priority(priority), module=module_obj, cycle=cycle_obj,
            estimate=estimate, branch=branch, from_branch=from_branch, to_branch=to_branch,
        )
        return vars(item)
    finally:
        session.close()


@mcp.tool()
def work_item_update(
    identifier: str,
    title: str | None = None,
    description: str | None = None,
    description_append: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    module: str | None = None,
    cycle: str | None = None,
    branch: str | None = None,
    from_branch: str | None = None,
    to_branch: str | None = None,
) -> dict:
    session, svc = service()
    try:
        module_obj = svc.modules.get(module) if module else None
        cycle_obj = svc.cycles.get(cycle) if cycle else None
        item = svc.update_task(
            identifier, title=title, description=description,
            append=description_append, status=status, priority=priority,
            module=module_obj, cycle=cycle_obj, branch=branch,
            from_branch=from_branch, to_branch=to_branch,
        )
        return vars(item)
    finally:
        session.close()


@mcp.tool()
def board(module: str | None = None, cycle: str | None = None) -> dict:
    from nod.domain.enums import WorkItemStatus
    session, svc = service()
    try:
        module_obj = svc.modules.get(module) if module else None
        cycle_obj = svc.cycles.get(cycle) if cycle else None
        items = svc.items.list(svc.project.id, module=module_obj, cycle=cycle_obj)
        return {
            status.value: [
                {"identifier": x.identifier, "title": x.title, "priority": x.priority.value, "estimate": x.estimate}
                for x in items if x.status == status
            ]
            for status in WorkItemStatus
        }
    finally:
        session.close()


@mcp.tool()
def timeline() -> list[dict]:
    session, svc = service()
    try:
        rows = []
        for c in svc.cycles.list():
            items = svc.items.list(svc.project.id, cycle=c)
            total = sum(i.estimate or 0 for i in items)
            rows.append({
                "slug": c.slug, "name": c.name, "status": c.status.value,
                "start": c.start_date, "end": c.end_date,
                "items": len(items), "estimate_h": round(total, 1),
            })
        return rows
    finally:
        session.close()


@mcp.tool()
def dependency_graph() -> dict:
    session, svc = service()
    try:
        g = svc.graph()
        return {
            "nodes": [{"id": n, **attrs} for n, attrs in g.nodes(data=True)],
            "edges": [{"source": s, "target": t, **attrs} for s, t, attrs in g.edges(data=True)],
        }
    finally:
        session.close()


def main():
    mcp.run()
