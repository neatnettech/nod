from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session


class Base(DeclarativeBase):
    pass


def database_url(root: Path) -> str:
    return f"sqlite:///{root / '.nod' / 'nod.db'}"


def create_session_factory(root: Path):
    nod_dir = root / ".nod"
    nod_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        database_url(root),
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


def create_schema(root: Path) -> None:
    from .models import Base as ModelBase
    factory = create_session_factory(root)
    ModelBase.metadata.create_all(factory.kw["bind"])
