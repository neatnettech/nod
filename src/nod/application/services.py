from pathlib import Path
import re
from uuid import UUID, uuid4

import networkx as nx
from sqlalchemy import select

from nod.domain.enums import (
    CycleStatus,
    ModuleStatus,
    Priority,
    RelationType,
    WorkItemStatus,
    WorkItemType,
)
from nod.domain.errors import DependencyCycleError, NotFoundError, ValidationError
from nod.domain.models import Cycle, Module, WorkItem
from nod.infrastructure.models import WorkItemRelationModel


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

    def create_task(self, title: str, description=None, type_=WorkItemType.TASK, priority=Priority.MEDIUM, module=None, cycle=None, estimate=None, status=None, branch=None):
        if not title.strip():
            raise ValidationError("Task title cannot be empty.")
        sequence = self.items.next_sequence(self.project.id)
        item = WorkItem(
            uuid4(), self.project.id, sequence,
            f"{self.project.identifier}-{sequence}", title.strip(),
            description=description, type=type_, priority=priority,
            module_id=module.id if module else None,
            cycle_id=cycle.id if cycle else None,
            estimate=estimate,
            status=status or WorkItemStatus.TODO,
            branch_name=branch,
        )
        self.items.add(item)
        self.session.commit()
        return item

    def update_task(
        self, identifier: str, title=None, description=None, append=None,
        status=None, priority=None, module=None, cycle=None, branch=None, estimate=None
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
            item.status = WorkItemStatus(status)
        if priority is not None:
            item.priority = Priority(priority)
        if module is not None:
            item.module_id = module.id
        if cycle is not None:
            item.cycle_id = cycle.id
        if branch is not None:
            item.branch_name = branch
        if estimate is not None:
            item.estimate = estimate
        self.items.update(item)
        self.session.commit()
        return item

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

    def graph(self):
        from nod.infrastructure.models import WorkItemRelationModel, WorkItemModel
        graph = nx.DiGraph()
        items = self.items.list(self.project.id)
        modules = {m.id: m.slug for m in self.modules.list()}
        for item in items:
            graph.add_node(
                item.identifier,
                title=item.title,
                status=item.status.value,
                priority=item.priority.value,
                description=item.description or "",
                branch=item.branch_name,
                module=modules.get(item.module_id),
            )
        rows = self.session.scalars(select(WorkItemRelationModel)).all()
        for row in rows:
            source = self.session.get(WorkItemModel, row.source_work_item_id)
            target = self.session.get(WorkItemModel, row.target_work_item_id)
            if source and target:
                graph.add_edge(source.identifier, target.identifier, relation=row.relation_type)
        return graph
