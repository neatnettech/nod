import os
import subprocess
from pathlib import Path

from sqlalchemy import create_engine, event
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

    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def create_schema(db: Path) -> None:
    from .models import Base as ModelBase
    db.parent.mkdir(parents=True, exist_ok=True)
    factory = create_session_factory(db)
    ModelBase.metadata.create_all(factory.kw["bind"])
