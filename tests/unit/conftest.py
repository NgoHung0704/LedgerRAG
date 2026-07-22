import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from tablerag.storage.orm import Base


@pytest.fixture
def db_session():
    """In-memory SQLite session; the ORM uses JSON/Uuid variants that work
    on both Postgres and SQLite."""
    engine = create_engine("sqlite://")

    # SQLite ignores FK constraints (and their ON DELETE CASCADE) unless asked
    # per-connection. Enable it so tests exercise the SAME cascade Postgres
    # enforces in production — e.g. delete_kb relying on the KB→session cascade.
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
