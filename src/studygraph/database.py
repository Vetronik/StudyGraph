from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from studygraph.config import get_database_url
from studygraph.document_model import Base

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine

    if _engine is None:
        _engine = create_engine(get_database_url(), pool_pre_ping=True)

    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory

    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
        )

    return _session_factory


def get_session() -> Generator[Session]:
    with get_session_factory() as session:
        yield session


def create_database_tables() -> None:
    Base.metadata.create_all(get_engine())
