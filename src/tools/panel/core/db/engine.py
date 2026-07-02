from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Engine

from tools.config import load_settings

settings = load_settings()
engine = create_engine(settings.database.url)
SessionLocal = sessionmaker(bind=engine)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable FK enforcement on SQLite (off by default; Postgres ignores this)."""
    if engine.dialect.name == "sqlite":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()