from pathlib import Path
import json
import re
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import networkx as nx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from nod.domain.enums import (
    INITIAL_STATUSES,
    TRANSITIONS,
    CycleStatus,
    ModuleStatus,
    Priority,
    RelationType,
    WorkItemStatus,
    WorkItemType,
)
from nod.domain.errors import DependencyCycleError, NotFoundError, ValidationError

from nod.domain.models import Cycle, Module, StatusChange, WorkItem
from nod.infrastructure.models import ActivityModel, WorkItemModel, WorkItemRelationModel


def due_date(value: str | None) -> str | None:
    """A due date normalized to YYYY-MM-DD; None leaves it unset, an empty string clears it."""
    if not value:
        return value
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValidationError(f"Due date must be YYYY-MM-DD, got {value!r}.") from None


def timestamp(value: str | None, label: str = "Completed at") -> datetime | None:
    """A UTC timestamp parsed from an ISO 8601 string: another zone is converted, no zone is read as UTC.
    An empty string clears it."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"{label} must be an ISO 8601 datetime, got {value!r}.") from None
    # SQLite keeps the wall clock and drops the zone, so everything is normalized before it is stored
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def today() -> str:
    """Today's date in UTC, YYYY-MM-DD. Every clock in nod is UTC, so two machines agree on what is overdue."""
    return utcnow().date().isoformat()


def _names(statuses) -> str:
    return ", ".join(s.value for s in WorkItemStatus if s in statuses)


def work_item_status(value) -> WorkItemStatus:
    try:
        return WorkItemStatus(value)
    except ValueError:
        raise ValidationError(f"Unknown status {value!r}. Use one of: {_names(WorkItemStatus)}.") from None


def stage_seconds(changes) -> dict[str, float]:
    """Seconds spent in each status, from one item's history in order. Only finished stays count:
    the status the item is in now is still running."""
    total: dict[str, float] = {}
    for entered, left in zip(changes, changes[1:]):
        total[entered.to_status] = total.get(entered.to_status, 0) + (left.at - entered.at).total_seconds()
    return total


def is_overdue(item) -> bool:
    """Past its due date and still open. Derived on read, never stored."""
    open_ = item.status not in (WorkItemStatus.DONE, WorkItemStatus.CANCELLED)
    return bool(item.due_date) and open_ and item.due_date < today()


def missing_placement(item) -> list[str]:
    """What an orphaned item lacks: its module, its cycle, or both. Empty when placed."""
    return [name for name, ref in (("module", item.module_id), ("cycle", item.cycle_id)) if ref is None]


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


class Services:
    def __init__(self, session, project):
        from nod.infrastructure.repositories import (
            CycleRepository,
            ModuleRepository,
            WorkItemRepository,
        )
        self.session = session
        self.project = project
        self.modules = ModuleRepository(session)
        self.cycles = CycleRepository(session)
        self.items = WorkItemRepository(session)

    def create_module(self, name: str, description=None) -> Module:
        if not name.strip():
            raise ValidationError("Module name cannot be empty.")
        module = Module(uuid4(), self.project.id, name.strip(), slugify(name), description=description)
        self.modules.add(module)
        self.session.commit()
        return module

    def update_module(self, ref: str, title=None, description=None, append=None, status=None, start=None, target=None):
        module = self.modules.get(ref)
        if not module:
            raise NotFoundError(f"Module not found: {ref}")
        if title is not None:
            module.name = title.strip()
        if description is not None:
            module.description = description
        if append is not None:
            module.description = ((module.description or "").rstrip() + "\n\n" + append.strip()).strip()
        if status is not None:
            module.status = ModuleStatus(status)
        self.modules.update(module)
        self.session.commit()
        return module

    def create_cycle(self, name: str, start=None, end=None, description=None) -> Cycle:
        if not name.strip():
            raise ValidationError("Cycle name cannot be empty.")
        if start and end and start > end:
            raise ValidationError("Cycle start date cannot be after end date.")
        cycle = Cycle(uuid4(), self.project.id, name.strip(), slugify(name), description=description, start_date=start, end_date=end)
        self.cycles.add(cycle)
        self.session.commit()
        return cycle

    def update_cycle(self, ref: str, title=None, description=None, append=None, status=None, start=None, end=None):
        cycle = self.cycles.get(ref)
        if not cycle:
            raise NotFoundError(f"Cycle not found: {ref}")
        new_start = start if start is not None else cycle.start_date
        new_end = end if end is not None else cycle.end_date
        if new_start and new_end and new_start > new_end:
            raise ValidationError("Cycle start date cannot be after end date.")
        if title is not None:
            cycle.name = title.strip()
        if description is not None:
            cycle.description = description
        if append is not None:
            cycle.description = ((cycle.description or "").rstrip() + "\n\n" + append.strip()).strip()
        if status is not None:
            cycle.status = CycleStatus(status)
        cycle.start_date, cycle.end_date = new_start, new_end
        self.cycles.update(cycle)
        self.session.commit()
        return cycle

    def create_task(self, title: str, description=None, type_=WorkItemType.TASK, priority=Priority.MEDIUM, module=None, cycle=None, estimate=None, status=None, branch=None, from_branch=None, to_branch=None, due=None, plan=None, memory=None, parent=None):
        if not title.strip():
            raise ValidationError("Task title cannot be empty.")
        status = work_item_status(status) if status else WorkItemStatus.TODO
        if status not in INITIAL_STATUSES:
            raise ValidationError(
                f"A new item cannot start as {status.value}. Create it as {_names(INITIAL_STATUSES)} and move it from there."
            )
        now = utcnow()
        for attempt in range(5):  # ponytail: SQLite serializes writers (busy_timeout); the loser rereads max(seq)
            sequence = self.items.next_sequence(self.project.id)
            item = WorkItem(
                uuid4(), self.project.id, sequence,
                f"{self.project.identifier}-{sequence}", title.strip(),
                description=description, type=type_, priority=priority,
                module_id=module.id if module else None,
                cycle_id=cycle.id if cycle else None,
                parent_id=parent.id if parent else None,
                estimate=estimate,
                status=status,
                branch_name=branch,
                from_branch=from_branch,
                to_branch=to_branch,
                due_date=due_date(due) or None,
                started_at=now if status is WorkItemStatus.IN_PROGRESS else None,
                plan_path=plan or None,
                memory_path=memory or None,
            )
            self.items.add(item)
            try:
                self.session.flush()  # the item row first: the log entry points at it
                self._record(item, None, status, now)
                self.session.commit()
                return item
            except IntegrityError:
                self.session.rollback()
                if attempt == 4:
                    raise

    def update_task(
        self, identifier: str, title=None, description=None, append=None,
        status=None, priority=None, module=None, cycle=None, branch=None, estimate=None,
        from_branch=None, to_branch=None, due=None, completed=None, plan=None, memory=None,
        parent=None, clear_parent: bool = False, started=None,
    ):
        item = self.items.get(self.project.id, identifier)
        if not item:
            raise NotFoundError(f"Work Item not found: {identifier}")
        if title is not None:
            item.title = title.strip()
        if description is not None:
            item.description = description
        if append is not None:
            item.description = ((item.description or "").rstrip() + "\n\n" + append.strip()).strip()
        if status is not None:
            self._move(item, work_item_status(status))
        if priority is not None:
            item.priority = Priority(priority)
        if module is not None:
            item.module_id = module.id
        if cycle is not None:
            item.cycle_id = cycle.id
        if parent is not None:
            self._check_parent(item, parent)
            item.parent_id = parent.id
        elif clear_parent:
            item.parent_id = None
        if branch is not None:
            item.branch_name = branch
        if from_branch is not None:
            item.from_branch = from_branch
        if to_branch is not None:
            item.to_branch = to_branch
        if due is not None:
            item.due_date = due_date(due) or None
        if started is not None:
            item.started_at = timestamp(started, "Started at")
        if completed is not None:
            item.completed_at = timestamp(completed)
        if started is not None or completed is not None:  # a hand set stamp has to fit the stage the item is in
            if item.started_at and item.status in (WorkItemStatus.BACKLOG, WorkItemStatus.TODO):
                raise ValidationError(f"{item.identifier} is {item.status.value}: it has not started, so it cannot have a start time.")
            if item.completed_at and item.status is not WorkItemStatus.DONE:
                raise ValidationError(f"{item.identifier} is {item.status.value}: only a done item can have a completion time.")
            if item.started_at and item.completed_at and item.completed_at < item.started_at:
                raise ValidationError("Completed at cannot be before started at.")
        if plan is not None:
            item.plan_path = plan or None
        if memory is not None:
            item.memory_path = memory or None
        if estimate is not None:
            item.estimate = estimate
        self.items.update(item)
        self.session.commit()
        return item

    def _move(self, item, new: WorkItemStatus) -> None:
        """Apply one allowed status change and the timestamps that follow from it. The same status is a no op."""
        if new is item.status:
            return
        if new not in TRANSITIONS[item.status]:
            raise ValidationError(
                f"{item.identifier} cannot go from {item.status.value} to {new.value}. "
                f"From {item.status.value} it can go to: {_names(TRANSITIONS[item.status])}."
            )
        now = utcnow()
        self._record(item, item.status, new, now)
        item.status = new
        if new is WorkItemStatus.IN_PROGRESS:
            item.started_at = item.started_at or now  # hold, resume and reopen keep the first start
        elif new in (WorkItemStatus.TODO, WorkItemStatus.BACKLOG):
            item.started_at = None  # handed back: it is not started any more
        item.completed_at = now if new is WorkItemStatus.DONE else None

    def _record(self, item, old, new, at) -> None:
        """Append one status change to the activity log. Written in the same commit as the change itself."""
        self.session.add(ActivityModel(
            project_id=str(self.project.id), work_item_id=str(item.id), event_type="status",
            payload=json.dumps({"from": old.value if old else None, "to": new.value}), created_at=at,
        ))

    def history(self, item=None, limit: int | None = None) -> list[StatusChange]:
        """Recorded status changes, oldest first: of one item, or of the whole project.
        limit keeps the most recent ones. Items that moved before the log existed have no entries."""
        stmt = (
            select(ActivityModel, WorkItemModel.identifier)
            .join(WorkItemModel, WorkItemModel.id == ActivityModel.work_item_id)
            .where(ActivityModel.project_id == str(self.project.id), ActivityModel.event_type == "status")
            .order_by(ActivityModel.created_at.desc(), ActivityModel.id)
        )
        if item is not None:
            stmt = stmt.where(ActivityModel.work_item_id == str(item.id))
        if limit:
            stmt = stmt.limit(limit)
        changes = []
        for row, identifier in self.session.execute(stmt).all():
            payload = json.loads(row.payload)
            # SQLite hands DateTime(timezone=True) back naive; it was written as UTC
            changes.append(StatusChange(row.id, identifier, payload["from"], payload["to"], row.created_at.replace(tzinfo=timezone.utc)))
        return changes[::-1]

    def worked(self) -> dict[str, float]:
        """Seconds each item spent in progress, by identifier: hold and waiting time left out."""
        by_item: dict[str, list[StatusChange]] = {}
        for change in self.history():
            by_item.setdefault(change.identifier, []).append(change)
        return {
            identifier: seconds
            for identifier, changes in by_item.items()
            if (seconds := stage_seconds(changes).get(WorkItemStatus.IN_PROGRESS.value))
        }

    def add_dependency(self, source: str, target: str):
        source_item = self.items.get(self.project.id, source)
        target_item = self.items.get(self.project.id, target)
        if not source_item or not target_item:
            raise NotFoundError("Both Work Items must exist.")

        graph = self._dependency_graph()
        graph.add_edge(source_item.identifier, target_item.identifier)
        if not nx.is_directed_acyclic_graph(graph):
            raise DependencyCycleError("Dependency would create a cycle.")

        self.session.add(WorkItemRelationModel(
            source_work_item_id=str(source_item.id),
            target_work_item_id=str(target_item.id),
            relation_type=RelationType.DEPENDS_ON.value,
        ))
        self.session.commit()

    def _dependency_graph(self):
        graph = nx.DiGraph()
        rows = self.session.scalars(
            select(WorkItemRelationModel).where(
                WorkItemRelationModel.relation_type == RelationType.DEPENDS_ON.value
            )
        ).all()
        for row in rows:
            source = self.session.get(__import__("nod.infrastructure.models", fromlist=["WorkItemModel"]).WorkItemModel, row.source_work_item_id)
            target = self.session.get(__import__("nod.infrastructure.models", fromlist=["WorkItemModel"]).WorkItemModel, row.target_work_item_id)
            if source and target:
                graph.add_edge(source.identifier, target.identifier)
        return graph

    def scope(self, module: str | None = None, cycle: str | None = None):
        """Resolve optional module and cycle slugs. An unknown slug is an error, never a
        silently unfiltered (or unassigned) result."""
        module_obj = self.modules.get(module) if module else None
        if module and module_obj is None:
            raise NotFoundError(f"Module not found: {module}")
        cycle_obj = self.cycles.get(cycle) if cycle else None
        if cycle and cycle_obj is None:
            raise NotFoundError(f"Cycle not found: {cycle}")
        return module_obj, cycle_obj

    def parent(self, ref: str | None):
        """Resolve a parent identifier (an epic). Unknown or non-epic is an error."""
        if not ref:
            return None
        obj = self.items.get(self.project.id, ref)
        if obj is None:
            raise NotFoundError(f"Parent not found: {ref}")
        if obj.type is not WorkItemType.EPIC:
            raise ValidationError(f"Parent {obj.identifier} is a {obj.type.value}, not an epic.")
        return obj

    def _check_parent(self, item, parent) -> None:
        node = parent
        while node is not None:  # self parent and loops: item must not be on the parent's ancestor chain
            if node.id == item.id:
                raise ValidationError(f"{item.identifier} cannot be its own ancestor.")
            node = self.items.get_by_id(node.parent_id) if node.parent_id else None

    def children(self, item):
        return self.items.list(self.project.id, parent=item)

    def graph(self, module=None, cycle=None, orphaned: bool = False):
        """Dependency graph of the items in scope (a resolved module and/or cycle). A
        prerequisite outside the scope is not drawn; the item lists it under
        ``needs_outside`` so a blocker in another release or area stays visible."""
        from nod.infrastructure.models import WorkItemRelationModel, WorkItemModel
        graph = nx.DiGraph()
        items = self.items.list(self.project.id)
        modules = {m.id: m.slug for m in self.modules.list()}
        idents = {i.id: i.identifier for i in items}
        for item in items:
            graph.add_node(
                item.identifier,
                title=item.title,
                status=item.status.value,
                priority=item.priority.value,
                description=item.description or "",
                branch=item.branch_name,
                from_branch=item.from_branch,
                to_branch=item.to_branch,
                due_date=item.due_date,
                overdue=is_overdue(item),
                missing=missing_placement(item),
                module=modules.get(item.module_id),
                parent=idents.get(item.parent_id),
            )
        rows = self.session.scalars(select(WorkItemRelationModel)).all()
        for row in rows:
            source = self.session.get(WorkItemModel, row.source_work_item_id)
            target = self.session.get(WorkItemModel, row.target_work_item_id)
            if source and target:
                graph.add_edge(source.identifier, target.identifier, relation=row.relation_type)
        if module is None and cycle is None and not orphaned:
            return graph
        keep = {i.identifier for i in self.items.list(self.project.id, module=module, cycle=cycle, orphaned=orphaned)}
        for n in keep:
            # depends_on points at the prerequisite, blocks points away from it
            needs = [v for v in graph.successors(n) if graph.edges[n, v].get("relation") == "depends_on"]
            needs += [u for u in graph.predecessors(n) if graph.edges[u, n].get("relation") == "blocks"]
            graph.nodes[n]["needs_outside"] = sorted(x for x in needs if x not in keep)
        return graph.subgraph(keep).copy()
