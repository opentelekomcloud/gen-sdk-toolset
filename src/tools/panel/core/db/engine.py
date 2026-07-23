from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from tools.config import load_settings

SessionLocal = sessionmaker()


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create the configured PostgreSQL engine once and bind the session factory.

    Deferred (not created at import time) so migrations and the API can boot
    without constructing an engine until a database connection is needed.
    ``pool_pre_ping`` transparently replaces connections dropped by the server.
    """
    engine = create_engine(load_settings().database.url, pool_pre_ping=True)
    SessionLocal.configure(bind=engine)
    return engine
