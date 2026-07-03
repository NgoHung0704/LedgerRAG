import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tablerag.storage.orm import Base


@pytest.fixture
def db_session():
    """In-memory SQLite session; the ORM uses JSON/Uuid variants that work
    on both Postgres and SQLite."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
