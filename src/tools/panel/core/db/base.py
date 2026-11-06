import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)


def violated_constraint(error: IntegrityError) -> str | None:
    """The name of the constraint the database reported broken, if it said.

    Read from the PostgreSQL error's diagnostics, which psycopg and psycopg2
    both expose as ``diag.constraint_name``, so a caller compares names rather
    than the error classes of one driver.
    """
    diagnostics = getattr(error.orig, "diag", None)
    return getattr(diagnostics, "constraint_name", None)
