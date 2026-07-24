"""FastAPI dependencies for the panel API."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from tools.panel.core.db.engine import SessionLocal, get_engine


def get_db() -> Iterator[Session]:
    """Yield a request-scoped SQLAlchemy session bound to the panel engine."""
    get_engine()  # ensure SessionLocal is bound before first use
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
