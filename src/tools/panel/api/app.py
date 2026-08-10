import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.exc import InterfaceError, OperationalError
from starlette.middleware.cors import CORSMiddleware

from tools.config import load_settings
from tools.panel.api.errors import register_error_handlers
from tools.panel.api.routes.health import router as health_router
from tools.panel.api.routes.scan_read import router as scan_read_router
from tools.panel.api.routes.scans import router as scan_router
from tools.panel.core.jobs import terminate_orphaned_jobs

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Close Jobs the previous process left behind, then serve.

    Scans run in ``BackgroundTasks``, so nothing survives a restart: a Job still
    marked ``queued`` or ``running`` has no thread behind it and will never
    finish on its own. Left alone it also blocks its service permanently, since
    ``uq_active_scan_job_per_service`` allows only one active scan job per
    service.

    Only the failures we actually expect are caught, and they are the
    operational ones: the database being unreachable or refusing the connection.
    Those are somebody else's to fix, the panel still serves every read endpoint
    without the cleanup, and refusing to boot would take the whole panel down
    over a janitorial step - the compose service has no ``restart`` policy, so
    it would stay down.

    Everything else propagates and stops startup on purpose. A ``TypeError`` or
    a constraint violation in here is our bug, and a bug that no-ops silently on
    every boot is exactly what this project treats as the expensive kind of
    failure.

    Degrading is not the same as ignoring: the outcome is recorded so ``/health``
    stops reporting ``ok``.
    """
    app.state.startup_cleanup_failed = False
    try:
        terminate_orphaned_jobs()
    except (OperationalError, InterfaceError):
        logger.exception(
            "startup: could not reach the database to terminate orphaned jobs — "
            "services with a job left running may refuse a rescan until it is "
            "cancelled"
        )
        app.state.startup_cleanup_failed = True
    yield


def create_app() -> FastAPI:
    settings = load_settings()

    app = FastAPI(title="Panel API", lifespan=_lifespan)
    # Set before the lifespan runs: `/health` is reachable in tests and tooling
    # that never enter the lifespan, and it must not have to guess.
    app.state.startup_cleanup_failed = False
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.panel.frontend_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    # Order matters: the read router ends with a `{repo:path}` catch-all, so it
    # is registered after the routes that carry a suffix.
    app.include_router(scan_router, prefix="/api")
    app.include_router(scan_read_router, prefix="/api")

    register_error_handlers(app)
    return app
