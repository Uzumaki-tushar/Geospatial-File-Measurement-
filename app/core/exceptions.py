"""Custom exception types and global HTTP exception handlers."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class GeoAPIError(Exception):
    """Base class for all application errors."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class FileTooLargeError(GeoAPIError):
    def __init__(self, max_mb: int) -> None:
        super().__init__(f"File exceeds maximum allowed size of {max_mb} MB.", status_code=413)


class UnsupportedFileTypeError(GeoAPIError):
    def __init__(self, received: str) -> None:
        super().__init__(
            f"Unsupported file type '{received}'. Only .kml and .zip files are accepted.",
            status_code=415,
        )


class FileNotFoundError(GeoAPIError):  # noqa: N818
    def __init__(self, file_id: str) -> None:
        super().__init__(f"File with id '{file_id}' not found.", status_code=404)


class FileProcessingError(GeoAPIError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422)


class FileNotReadyError(GeoAPIError):
    def __init__(self, file_id: str, status: str) -> None:
        super().__init__(
            f"File '{file_id}' is not in COMPLETED state (current: {status}).",
            status_code=409,
        )


class ZipSlipError(GeoAPIError):
    def __init__(self) -> None:
        super().__init__("Malicious zip archive detected (path traversal).", status_code=422)


# ---------------------------------------------------------------------------
# Error handler registration
# ---------------------------------------------------------------------------


def _error_body(message: str, status_code: int) -> dict:
    return {"error": {"status_code": status_code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    """Attach global exception handlers to the FastAPI app."""

    @app.exception_handler(GeoAPIError)
    async def geo_api_error_handler(request: Request, exc: GeoAPIError) -> JSONResponse:
        logger.warning("GeoAPIError [%d]: %s", exc.status_code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.message, exc.status_code),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url)
        return JSONResponse(
            status_code=500,
            content=_error_body("An internal server error occurred.", 500),
        )
