"""Local, read only live dashboard behind `nod serve`: `/` is the overview, `/cycle/<slug>`
one cycle, `/unplanned` the items in no cycle, `/item/<identifier>` one work item."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote
from uuid import uuid4

from nod.application.services import Services, today
from nod.cli.report import render_cycle, render_dashboard, render_item
from nod.domain.enums import CycleStatus
from nod.domain.models import Cycle
from nod.infrastructure.repositories import ProjectRepository


def current_cycle(services, ref: str | None = None):
    """The named cycle, else the active one, else an open one whose dates include today."""
    if ref:
        return services.cycles.get(ref)
    cycles = services.cycles.list()
    now = today()
    open_ = [c for c in cycles if c.status in (CycleStatus.ACTIVE, CycleStatus.UPCOMING)]
    return next(
        (c for c in open_ if c.status == CycleStatus.ACTIVE),
        next((c for c in open_ if c.start_date and c.end_date and c.start_date <= now <= c.end_date), None),
    )


def item_page(services, project, item, modules) -> str:
    graph = services.graph()
    by_identifier = {x.identifier: x for x in services.items.list(project.id)}
    me = item.identifier

    def linked(relation_out, relation_in):
        """Items reached by an outgoing edge of one relation or an incoming edge of the other."""
        out = [v for v in graph.successors(me) if graph.edges[me, v].get("relation") == relation_out]
        out += [u for u in graph.predecessors(me) if graph.edges[u, me].get("relation") == relation_in]
        return [by_identifier[i] for i in sorted(set(out), key=lambda i: by_identifier[i].sequence_id)]

    return render_item(
        project, item,
        module=next((m for m in modules if m.id == item.module_id), None),
        cycle=next((c for c in services.cycles.list() if c.id == item.cycle_id), None),
        parent=services.items.get_by_id(item.parent_id) if item.parent_id else None,
        children=services.children(item),
        # depends_on points at the prerequisite, blocks points away from it
        needs=linked("depends_on", "blocks"),
        unblocks=linked("blocks", "depends_on"),
        history=services.history(item),
    )


def make_server(factory, port: int = 8765, ref: str | None = None) -> ThreadingHTTPServer:
    def page(path: str) -> str | None:
        # a fresh session per request, so every load sees what other processes committed
        with factory() as session:
            project = ProjectRepository(session).get()
            services = Services(session, project)
            modules = services.modules.list()
            if path == "/":
                return render_dashboard(
                    project, services.cycles.list(), services.items.list(project.id), modules,
                    current=current_cycle(services, ref),
                    activity=services.history(limit=8), worked=services.worked(),
                )
            if path == "/unplanned":
                cycle = Cycle(uuid4(), project.id, "No cycle", "unplanned", status=CycleStatus.UPCOMING)
                items = [x for x in services.items.list(project.id) if x.cycle_id is None]
                return render_cycle(project, cycle, items, modules, live=True)
            if path.startswith("/cycle/") and (cycle := services.cycles.get(path.removeprefix("/cycle/"))):
                return render_cycle(project, cycle, services.items.list(project.id, cycle=cycle), modules, live=True)
            if path.startswith("/item/") and (item := services.items.get(project.id, unquote(path.removeprefix("/item/")))):
                return item_page(services, project, item, modules)
            return None

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            html = page(self.path.split("?")[0])
            status, content_type, body = (200, "text/html", html) if html else (404, "text/plain", "Not found")
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    # loopback only: the page is an unauthenticated view of the project
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
