from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from tools.config import load_settings
from tools.panel.api.errors import register_error_handlers
from tools.panel.api.routes.health import router as health_router


def create_app() -> FastAPI:
    settings = load_settings()

    app = FastAPI(title="Panel API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.panel.frontend_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    # app.include_router(scan_router, prefix="/api")

    register_error_handlers(app)
    return app
