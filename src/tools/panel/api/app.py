import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
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

    A failure here must not stop the panel from starting. Every read endpoint
    works without the cleanup, and a database that is unreachable at boot is an
    operational problem to surface in the log rather than a reason to refuse to
    serve.
    """
    try:
        terminate_orphaned_jobs()
    except Exception:
        logger.exception("startup: could not terminate orphaned jobs")
    yield


def create_app() -> FastAPI:
    settings = load_settings()

    app = FastAPI(title="Panel API", lifespan=_lifespan)
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
