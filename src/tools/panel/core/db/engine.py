from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from tools.config import load_settings

SessionLocal = sessionmaker()


def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable FK enforcement on SQLite (off by default; Postgres ignores this)."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create the configured engine once and bind the session factory.

    Deferred (not created at import time) so migrations and the API can boot
    without constructing an engine until a database connection is needed.
    """
    engine = create_engine(load_settings().database.url)
    SessionLocal.configure(bind=engine)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _set_sqlite_pragma)
    return engine
