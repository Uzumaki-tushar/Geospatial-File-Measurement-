"""
Geospatial File Measurement API — FastAPI application entrypoint.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import files as files_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.db.database import init_db
from app.schemas.file import HealthResponse
from app.utils.file_utils import ensure_dirs

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise database and storage directories on startup."""
    logger.info("Starting Geospatial Measurement API...")
    ensure_dirs(settings.upload_dir, settings.extract_dir)
    init_db()
    logger.info("Startup complete.")
    yield
    logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Geospatial File Measurement API",
    description=(
        "Upload a .kml or .zip Shapefile and receive accurate area/length "
        "measurements for every feature, automatically projected to the correct CRS."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS — open for local dev; restrict in production via env
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register global exception handlers
register_exception_handlers(app)

# Mount routers
app.include_router(files_router.router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Return the service health status."""
    return HealthResponse()
