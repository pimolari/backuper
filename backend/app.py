"""
Backuper API — application entry point.

Uses the factory pattern to build the FastAPI application with all
routers registered.  Run with::

    uvicorn backend.app:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes import auth_routes, profile_routes, file_routes


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    application = FastAPI(title="Backuper API", version="2.0.0")

    # ── CORS ──
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ──
    application.include_router(auth_routes.router)
    application.include_router(profile_routes.router)
    application.include_router(file_routes.router)

    return application


app = create_app()
