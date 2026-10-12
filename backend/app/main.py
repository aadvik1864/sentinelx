from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import (
    ai,
    alerts,
    assets,
    auth,
    dashboard,
    demo,
    events,
    incidents,
    passkeys,
    rules,
    settings,
    sources,
    threat_intel,
)
from app.core.clock import clock_guard
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.seed import bootstrap, seed_demo
from app.services.telemetry import record_request
from app.websocket.broker import broker
from app.websocket.broker import router as websocket_router

config = get_settings()


@asynccontextmanager
async def lifespan(app):
    app.state.clock_guard_enabled = config.environment == "production"
    if config.environment == "production":
        clock_guard.start()
    try:
        with SessionLocal() as db:
            if config.environment == "production":
                role = db.execute(
                    text(
                        "SELECT current_user, rolsuper, rolcreatedb, rolcreaterole, rolreplication, "
                        "rolbypassrls, has_schema_privilege(current_user, 'public', 'CREATE'), "
                        "has_database_privilege(current_user, current_database(), 'CREATE'), "
                        "EXISTS(SELECT 1 FROM pg_auth_members WHERE member=pg_roles.oid) "
                        "FROM pg_roles WHERE rolname=current_user"
                    )
                ).one()
                if role[0] != "sentinelx_runtime" or any(role[1:]):
                    raise RuntimeError(
                        "Production API requires the isolated least-privilege runtime role"
                    )
            else:
                bootstrap(db)
            if config.seed_demo and config.environment == "development":
                seed_demo(db)
        await broker.start()
        try:
            yield
        finally:
            await broker.stop()
    finally:
        clock_guard.stop()


app = FastAPI(
    title="SentinelX",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs"
    if config.api_docs_enabled and config.environment == "development"
    else None,
    redoc_url=None,
    openapi_url=(
        "/api/openapi.json"
        if config.api_docs_enabled and config.environment == "development"
        else None
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.hosts, www_redirect=False)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if (
        getattr(app.state, "clock_guard_enabled", False)
        and request.url.path not in {"/health/live", "/health/ready"}
        and not clock_guard.healthy()
    ):
        return JSONResponse(
            status_code=503,
            content={"detail": "Server clock requires operator review"},
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
            },
        )
    if request.method in {"POST", "PATCH", "DELETE"}:
        if (
            request.cookies.get("sentinelx_refresh")
            and request.headers.get("origin") not in config.origins
        ):
            return JSONResponse(status_code=403, content={"detail": "Invalid request origin"})
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 256 * 1024:
                return JSONResponse(
                    status_code=413, content={"detail": "Request body exceeds 256 KB"}
                )
        request._body = bytes(body)
    try:
        response = await call_next(request)
    except Exception:
        record_request(request, 500)
        raise
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    record_request(request, response.status_code)
    return response


@app.get("/health/live", include_in_schema=False)
def live():
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
def ready():
    if getattr(app.state, "clock_guard_enabled", False) and not clock_guard.healthy():
        return JSONResponse(status_code=503, content={"status": "clock_unstable"})
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        if broker.redis:
            broker.redis.ping()
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}


for module in [
    auth,
    passkeys,
    events,
    alerts,
    incidents,
    rules,
    assets,
    dashboard,
    threat_intel,
    ai,
    demo,
    settings,
    sources,
]:
    app.include_router(module.router, prefix="/api/v1")
app.include_router(websocket_router)
