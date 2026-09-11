"""
Main application entry point for the Flood Intelligence Platform (FIP) backend.

Wires FastAPI routing, CORS middleware, asynchronous database/redis connectivity checks,
and operational health telemetry.
"""

from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings, Settings
from backend.models.database import get_db
from backend.schemas.health import HealthResponse
from backend.api.routes.wards import router as wards_router
from backend.api.routes.weather import router as weather_router
from backend.api.routes.reports import router as reports_router
from backend.api.routes.alerts import router as alerts_router
from backend.api.routes.social import router as social_router
from backend.api.routes.signals import signals_router
from backend.api.routes.routing import routing_router
from backend.api.websocket import websocket_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Handle application startup and shutdown events.
    Verifies initial resources and logs operational status.
    """
    # Startup actions
    print(f"[{settings.app_name}] Starting in {settings.environment} mode...")
    try:
        from backend.models import Base, engine
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print(f"[{settings.app_name}] Database tables initialized/verified.")
    except Exception as e:
        print(f"[{settings.app_name}] Database schema check note: {e}")
    yield
    # Shutdown actions
    print(f"[{settings.app_name}] Shutting down gracefully...")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Geo-Intelligent Coastal & Urban Flood Intelligence Platform API",
    openapi_url="/v1/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configure Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Routers
app.include_router(wards_router, prefix="/v1")
app.include_router(weather_router, prefix="/v1")
app.include_router(reports_router, prefix="/v1")
app.include_router(alerts_router, prefix="/v1")
app.include_router(social_router, prefix="/v1")
app.include_router(signals_router, prefix="/v1")
app.include_router(routing_router, prefix="/v1")
app.include_router(websocket_router)


@app.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint",
    tags=["System"]
)
async def health_check(
    db: AsyncSession = Depends(get_db),
    app_settings: Settings = Depends(get_settings)
) -> HealthResponse:
    """
    Perform a health check evaluating database connectivity and service status.

    Returns the current operational status, UTC timestamp, and auxiliary telemetry.
    """
    db_status = "connected"
    try:
        # Asynchronously verify database query execution
        result = await db.execute(text("SELECT 1;"))
        _ = result.scalar()
    except Exception as exc:
        db_status = f"unreachable: {str(exc)}"

    overall_status = "ok" if db_status == "connected" else "degraded"

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.now(timezone.utc),
        version="1.0.0",
        services={
            "database": db_status,
            "environment": app_settings.environment,
            "debug": app_settings.debug
        }
    )


@app.get("/", tags=["System"])
async def root():
    """Service root endpoint returning basic API identity."""
    return {
        "service": settings.app_name,
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }
