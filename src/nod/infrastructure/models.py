from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def now():
    return datetime.now(timezone.utc)


class ProjectModel(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    identifier: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class MemberModel(Base):
    __tablename__ = "members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))


class ModuleModel(Base):
    __tablename__ = "modules"
    __table_args__ = (UniqueConstraint("project_id", "slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="planned", nullable=False)


class CycleModel(Base):
    __tablename__ = "cycles"
    __table_args__ = (UniqueConstraint("project_id", "slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="upcoming", nullable=False)
    start_date: Mapped[str | None] = mapped_column(String(10))
    end_date: Mapped[str | None] = mapped_column(String(10))


class WorkItemModel(Base):
    __tablename__ = "work_items"
    __table_args__ = (UniqueConstraint("project_id", "sequence_id"), UniqueConstraint("project_id", "identifier"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    sequence_id: Mapped[int] = mapped_column(Integer, nullable=False)
    identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(32), default="task", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="todo", nullable=False)
    priority: Mapped[str] = mapped_column(String(32), default="medium", nullable=False)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("work_items.id"))
    module_id: Mapped[str | None] = mapped_column(ForeignKey("modules.id"))
    cycle_id: Mapped[str | None] = mapped_column(ForeignKey("cycles.id"))
    assignee_id: Mapped[str | None] = mapped_column(ForeignKey("members.id"))
    estimate: Mapped[float | None] = mapped_column(Float)
    branch_name: Mapped[str | None] = mapped_column(String(255))
    from_branch: Mapped[str | None] = mapped_column(String(255))  # where the branch was cut from
    to_branch: Mapped[str | None] = mapped_column(String(255))    # where it merges
    due_date: Mapped[str | None] = mapped_column(String(10))      # YYYY-MM-DD, like cycle dates
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LabelModel(Base):
    __tablename__ = "labels"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class WorkItemLabelModel(Base):
    __tablename__ = "work_item_labels"

    work_item_id: Mapped[str] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"), primary_key=True)
    label_id: Mapped[str] = mapped_column(ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True)


class WorkItemRelationModel(Base):
    __tablename__ = "work_item_relations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_work_item_id: Mapped[str] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False)
    target_work_item_id: Mapped[str] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CommentModel(Base):
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    work_item_id: Mapped[str] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("members.id"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ActivityModel(Base):
    __tablename__ = "activity"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    work_item_id: Mapped[str | None] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"))
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("members.id"))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class GitRepositoryModel(Base):
    __tablename__ = "git_repositories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    root_path: Mapped[str] = mapped_column(Text, nullable=False)
