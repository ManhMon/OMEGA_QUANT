from fastapi import FastAPI, APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from omega.api.dependencies import MAX_REQUEST_BODY_BYTES
from omega.api.routes.macro import router as macro_router
from omega.api.routes.quant import router as quant_router
from omega.api.routes.portfolio import router as portfolio_router
from omega.api.routes.market import router as market_router
from omega.api.routes.stream import router as stream_router
from omega.api.routes.control import router as control_router, sse_control_router, get_strategy_backtest_report
from omega.api.routes.alpha import router as alpha_router, sse_alpha_router
from omega.api.routes.sentiment import router as sentiment_router
from omega.api.routes.risk_tca import router as risk_tca_router
from omega.api.routes.copilot import router as copilot_router, sse_copilot_router
from omega.api.routes.jobs import router as jobs_router
from omega.api.routes.models import router as models_router
from omega.api.routes.operations import router as operations_router
from omega.api.routes.execution import router as execution_router

strategy_router = APIRouter(prefix="/api/v1/strategy", tags=["strategy"])
strategy_router.add_api_route("/backtest/{strategy_id}", get_strategy_backtest_report, methods=["GET"])


def create_app() -> FastAPI:
    app = FastAPI(
        title="OMEGA_QUANT Telemetry & Data Bridge",
        description="FastAPI REST, WebSocket & SSE gateway for OMEGA_QUANT Dashboard",
        version="1.0.0",
    )

    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def enforce_request_size_limit(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH"}:
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    if int(content_length) > MAX_REQUEST_BODY_BYTES:
                        return JSONResponse(
                            status_code=413,
                            content={"detail": "Request body exceeds 512 KiB limit"},
                        )
                except ValueError:
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "Invalid Content-Length header"},
                    )
            body = await request.body()
            if len(body) > MAX_REQUEST_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body exceeds 512 KiB limit"},
                )
        return await call_next(request)

    # Include routers

    app.include_router(macro_router)
    app.include_router(quant_router)
    app.include_router(portfolio_router)
    app.include_router(market_router)
    app.include_router(stream_router)
    app.include_router(control_router)
    app.include_router(sse_control_router)
    app.include_router(alpha_router)
    app.include_router(sse_alpha_router)
    app.include_router(sentiment_router)
    app.include_router(risk_tca_router)
    app.include_router(copilot_router)
    app.include_router(sse_copilot_router)
    app.include_router(strategy_router)
    app.include_router(jobs_router)
    app.include_router(models_router)
    app.include_router(operations_router)
    app.include_router(execution_router)

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "service": "omega-api-bridge"}

    return app


app = create_app()
