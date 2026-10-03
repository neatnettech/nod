from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .enums import (
    CycleStatus,
    ModuleStatus,
    Priority,
    RelationType,
    WorkItemStatus,
    WorkItemType,
)
from .errors import InvalidDependencyError


@dataclass
class Project:
    id: UUID
    identifier: str
    name: str
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Member:
    id: UUID
    project_id: UUID
    name: str
    email: str | None = None


@dataclass
class Module:
    id: UUID
    project_id: UUID
    name: str
    slug: str
    description: str | None = None
    status: ModuleStatus = ModuleStatus.PLANNED


@dataclass
class Cycle:
    id: UUID
    project_id: UUID
    name: str
    slug: str
    description: str | None = None
    status: CycleStatus = CycleStatus.UPCOMING
    start_date: str | None = None
    end_date: str | None = None


@dataclass
class WorkItem:
    id: UUID
    project_id: UUID
    sequence_id: int
    identifier: str
    title: str
    description: str | None = None
    type: WorkItemType = WorkItemType.TASK
    status: WorkItemStatus = WorkItemStatus.TODO
    priority: Priority = Priority.MEDIUM
    parent_id: UUID | None = None
    module_id: UUID | None = None
    cycle_id: UUID | None = None
    assignee_id: UUID | None = None
    estimate: float | None = None
    branch_name: str | None = None
    from_branch: str | None = None
    to_branch: str | None = None
    due_date: str | None = None
    completed_at: datetime | None = None


@dataclass
class Relation:
    id: UUID
    source_work_item_id: UUID
    target_work_item_id: UUID
    relation_type: RelationType


def validate_dependency(source_id: UUID, target_id: UUID) -> None:
    if source_id == target_id:
        raise InvalidDependencyError("A work item cannot depend on itself.")
