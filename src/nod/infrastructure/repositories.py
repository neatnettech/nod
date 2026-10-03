from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nod.domain.enums import (
    CycleStatus,
    ModuleStatus,
    Priority,
    RelationType,
    WorkItemStatus,
    WorkItemType,
)
from nod.domain.models import Cycle, Module, Project, WorkItem
from .models import CycleModel, ModuleModel, ProjectModel, WorkItemModel


def _uuid(value: str) -> UUID:
    return UUID(value)


class ProjectRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self) -> Project | None:
        row = self.session.scalar(select(ProjectModel).limit(1))
        if not row:
            return None
        return Project(
            id=_uuid(row.id), identifier=row.identifier, name=row.name,
            description=row.description, created_at=row.created_at, updated_at=row.updated_at
        )

    def add(self, project: Project) -> None:
        self.session.add(ProjectModel(
            id=str(project.id), identifier=project.identifier, name=project.name,
            description=project.description
        ))


class ModuleRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(self) -> list[Module]:
        rows = self.session.scalars(select(ModuleModel).order_by(ModuleModel.name)).all()
        return [Module(_uuid(r.id), _uuid(r.project_id), r.name, r.slug, r.description, ModuleStatus(r.status)) for r in rows]

    def get(self, ref: str) -> Module | None:
        stmt = select(ModuleModel).where(ModuleModel.slug == ref)
        row = self.session.scalar(stmt)
        if not row:
            return None
        return Module(_uuid(row.id), _uuid(row.project_id), row.name, row.slug, row.description, ModuleStatus(row.status))

    def add(self, module: Module) -> None:
        self.session.add(ModuleModel(
            id=str(module.id), project_id=str(module.project_id), name=module.name,
            slug=module.slug, description=module.description, status=module.status.value
        ))

    def update(self, module: Module) -> None:
        row = self.session.get(ModuleModel, str(module.id))
        row.name = module.name
        row.description = module.description
        row.status = module.status.value


class CycleRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(self) -> list[Cycle]:
        rows = self.session.scalars(select(CycleModel).order_by(CycleModel.name)).all()
        return [Cycle(_uuid(r.id), _uuid(r.project_id), r.name, r.slug, r.description, CycleStatus(r.status), r.start_date, r.end_date) for r in rows]

    def get(self, ref: str) -> Cycle | None:
        row = self.session.scalar(select(CycleModel).where(CycleModel.slug == ref))
        if not row:
            return None
        return Cycle(_uuid(row.id), _uuid(row.project_id), row.name, row.slug, row.description, CycleStatus(row.status), row.start_date, row.end_date)

    def add(self, cycle: Cycle) -> None:
        self.session.add(CycleModel(
            id=str(cycle.id), project_id=str(cycle.project_id), name=cycle.name,
            slug=cycle.slug, description=cycle.description, status=cycle.status.value,
            start_date=cycle.start_date, end_date=cycle.end_date
        ))

    def update(self, cycle: Cycle) -> None:
        row = self.session.get(CycleModel, str(cycle.id))
        row.name = cycle.name
        row.description = cycle.description
        row.status = cycle.status.value
        row.start_date = cycle.start_date
        row.end_date = cycle.end_date


class WorkItemRepository:
    def __init__(self, session: Session):
        self.session = session

    def next_sequence(self, project_id: UUID) -> int:
        value = self.session.scalar(
            select(func.max(WorkItemModel.sequence_id)).where(WorkItemModel.project_id == str(project_id))
        )
        return (value or 0) + 1

    def list(self, project_id: UUID, status=None, module=None, cycle=None, priority=None, type_=None) -> list[WorkItem]:
        stmt = select(WorkItemModel).where(WorkItemModel.project_id == str(project_id)).order_by(WorkItemModel.sequence_id)
        if status:
            stmt = stmt.where(WorkItemModel.status == status.value)
        if module:
            stmt = stmt.where(WorkItemModel.module_id == str(module.id))
        if cycle:
            stmt = stmt.where(WorkItemModel.cycle_id == str(cycle.id))
        if priority:
            stmt = stmt.where(WorkItemModel.priority == priority.value)
        if type_:
            stmt = stmt.where(WorkItemModel.type == type_.value)
        rows = self.session.scalars(stmt).all()
        return [self._to_domain(r) for r in rows]

    def get(self, project_id: UUID, identifier: str) -> WorkItem | None:
        row = self.session.scalar(
            select(WorkItemModel).where(
                WorkItemModel.project_id == str(project_id),
                WorkItemModel.identifier == identifier.upper(),
            )
        )
        return self._to_domain(row) if row else None

    def add(self, item: WorkItem) -> None:
        self.session.add(WorkItemModel(
            id=str(item.id), project_id=str(item.project_id), sequence_id=item.sequence_id,
            identifier=item.identifier, title=item.title, description=item.description,
            type=item.type.value, status=item.status.value, priority=item.priority.value,
            parent_id=str(item.parent_id) if item.parent_id else None,
            module_id=str(item.module_id) if item.module_id else None,
            cycle_id=str(item.cycle_id) if item.cycle_id else None,
            assignee_id=str(item.assignee_id) if item.assignee_id else None,
            estimate=item.estimate,
            branch_name=item.branch_name,
            from_branch=item.from_branch,
            to_branch=item.to_branch,
        ))

    def update(self, item: WorkItem) -> None:
        row = self.session.get(WorkItemModel, str(item.id))
        if not row:
            return
        row.title = item.title
        row.description = item.description
        row.type = item.type.value
        row.status = item.status.value
        row.priority = item.priority.value
        row.module_id = str(item.module_id) if item.module_id else None
        row.cycle_id = str(item.cycle_id) if item.cycle_id else None
        row.assignee_id = str(item.assignee_id) if item.assignee_id else None
        row.estimate = item.estimate
        row.branch_name = item.branch_name
        row.from_branch = item.from_branch
        row.to_branch = item.to_branch

    def _to_domain(self, r: WorkItemModel) -> WorkItem:
        return WorkItem(
            id=_uuid(r.id), project_id=_uuid(r.project_id), sequence_id=r.sequence_id,
            identifier=r.identifier, title=r.title, description=r.description,
            type=WorkItemType(r.type), status=WorkItemStatus(r.status),
            priority=Priority(r.priority), parent_id=_uuid(r.parent_id) if r.parent_id else None,
            module_id=_uuid(r.module_id) if r.module_id else None,
            cycle_id=_uuid(r.cycle_id) if r.cycle_id else None,
            assignee_id=_uuid(r.assignee_id) if r.assignee_id else None,
            estimate=r.estimate,
            branch_name=r.branch_name, from_branch=r.from_branch, to_branch=r.to_branch,
            completed_at=r.completed_at
        )
