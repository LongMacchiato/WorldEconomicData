from collections.abc import Awaitable, Callable

from app.api.analytics_routes import analytics_router
from app.api.macro_routes import macro_router
from app.api.routes import router
from app.config import get_settings
from app.exceptions import (
    DatasetNotFoundError,
    DBnomicsBrowserError,
    InvalidAnalyticsQueryError,
    ProviderNotFoundError,
    ResultLimitExceededError,
    SeriesNotFoundError,
    UpstreamResponseError,
    UpstreamUnavailableError,
)
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

settings = get_settings()
app = FastAPI(title="WorldEconomicData API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
app.include_router(router, prefix="/api")
app.include_router(analytics_router, prefix="/api/analytics")
app.include_router(macro_router, prefix="/api/macro")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _error_handler(
    status_code: int, error_name: str
) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handler(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content={"error": error_name, "detail": str(error)},
        )

    return handler


app.add_exception_handler(
    ProviderNotFoundError,
    _error_handler(404, "provider_not_found"),
)
app.add_exception_handler(
    DatasetNotFoundError,
    _error_handler(404, "dataset_not_found"),
)
app.add_exception_handler(
    SeriesNotFoundError,
    _error_handler(404, "series_not_found"),
)
app.add_exception_handler(
    UpstreamUnavailableError,
    _error_handler(503, "upstream_unavailable"),
)
app.add_exception_handler(
    UpstreamResponseError,
    _error_handler(502, "upstream_response_error"),
)
app.add_exception_handler(
    ResultLimitExceededError,
    _error_handler(413, "result_limit_exceeded"),
)
app.add_exception_handler(
    InvalidAnalyticsQueryError,
    _error_handler(422, "invalid_analytics_query"),
)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(
    _request: Request, error: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "validation_error", "detail": str(error)},
    )


@app.exception_handler(DBnomicsBrowserError)
async def browser_error_handler(
    _request: Request, error: DBnomicsBrowserError
) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": "dbnomics_browser_error", "detail": str(error)},
    )
