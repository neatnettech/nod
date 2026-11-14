from enum import StrEnum


class WorkItemType(StrEnum):
    EPIC = "epic"
    STORY = "story"
    TASK = "task"
    BUG = "bug"


class WorkItemStatus(StrEnum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    HOLD = "hold"
    DONE = "done"
    CANCELLED = "cancelled"


# The only moves a work item may make. Stages run in order (backlog, todo, in progress, done);
# hold is the blocked side step, cancelled the way out, and each has a way back.
_S = WorkItemStatus
TRANSITIONS: dict[WorkItemStatus, frozenset[WorkItemStatus]] = {
    _S.BACKLOG: frozenset({_S.TODO, _S.CANCELLED}),
    _S.TODO: frozenset({_S.IN_PROGRESS, _S.BACKLOG, _S.CANCELLED}),
    _S.IN_PROGRESS: frozenset({_S.HOLD, _S.DONE, _S.TODO, _S.CANCELLED}),
    _S.HOLD: frozenset({_S.IN_PROGRESS, _S.TODO, _S.CANCELLED}),
    _S.DONE: frozenset({_S.IN_PROGRESS, _S.TODO}),
    _S.CANCELLED: frozenset({_S.BACKLOG, _S.TODO}),
}
# A new item cannot be born finished or blocked: there would be no start to measure from.
INITIAL_STATUSES = frozenset({_S.BACKLOG, _S.TODO, _S.IN_PROGRESS})


class Priority(StrEnum):
    NO_PRIORITY = "no_priority"
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ModuleStatus(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CycleStatus(StrEnum):
    UPCOMING = "upcoming"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RelationType(StrEnum):
    DEPENDS_ON = "depends_on"
    BLOCKS = "blocks"
    RELATED_TO = "related_to"
    DUPLICATES = "duplicates"
