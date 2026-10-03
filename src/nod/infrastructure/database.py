import os
import subprocess
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session


class Base(DeclarativeBase):
    pass


def db_path(cwd: Path | None = None) -> Path:
    """NOD_DB, else <main checkout>/.nod/nod.db (shared by every worktree), else <cwd>/.nod/nod.db."""
    if env := os.environ.get("NOD_DB"):
        return Path(env).expanduser().resolve()
    cwd = cwd or Path.cwd()
    out = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=cwd, capture_output=True, text=True,
    )
    common = Path(out.stdout.strip())
    # ponytail: bare repos and submodules (common dir not named .git) fall back to cwd
    root = common.parent if out.returncode == 0 and common.name == ".git" else cwd
    return root / ".nod" / "nod.db"


def database_url(db: Path) -> str:
    return f"sqlite:///{db}"


def create_session_factory(db: Path):
    engine = create_engine(
        database_url(db),
        connect_args={"check_same_thread": False, "timeout": 10},
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()

    migrate(engine)
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


# Schema changes made after databases already exist, in order. Each runs once per
# database, tracked by SQLite's user_version, so an existing .nod/nod.db upgrades in
# place on its next command. Append only: never edit or reorder an applied entry.
MIGRATIONS = [
    "ALTER TABLE work_items ADD COLUMN from_branch VARCHAR(255)",
    "ALTER TABLE work_items ADD COLUMN to_branch VARCHAR(255)",
    "ALTER TABLE work_items ADD COLUMN due_date VARCHAR(10)",
]


def migrate(engine) -> None:
    """Apply pending MIGRATIONS. A database with no tables yet is left to create_all."""
    with engine.begin() as conn:
        exists = conn.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'work_items'"
        ).first()
        if not exists:
            return
        version = conn.exec_driver_sql("PRAGMA user_version").scalar()
        for number, statement in enumerate(MIGRATIONS[version:], start=version + 1):
            try:
                conn.exec_driver_sql(statement)
            except OperationalError as exc:
                # a fresh create_all schema already has the column, or another nod
                # process applied it first: either way the change is in place
                if "duplicate column" not in str(exc):
                    raise
            conn.exec_driver_sql(f"PRAGMA user_version = {number}")


def create_schema(db: Path) -> None:
    from .models import Base as ModelBase
    db.parent.mkdir(parents=True, exist_ok=True)
    engine = create_session_factory(db).kw["bind"]
    ModelBase.metadata.create_all(engine)
    migrate(engine)  # stamps a fresh schema as current, upgrades an existing one
