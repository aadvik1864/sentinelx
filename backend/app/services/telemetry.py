"""Redacted JSON records from actual application activity, never from collection itself."""

import ipaddress
import json
import logging
import sys
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Request

from app.core.config import get_settings

logger = logging.getLogger("sentinelx.activity")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


def emit_activity(request: Request, event_type: str, message: str, **fields):
    if not get_settings().live_monitoring:
        return
    ip = request.client.host if request.client else None
    try:
        ip = str(ipaddress.ip_address(ip))
    except (ValueError, TypeError):
        ip = None
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event_type": event_type,
        "message": message,
        "ip": ip,
        "level": "INFO",
        "record_id": str(uuid4()),
        **fields,
    }
    # Only explicit fields are emitted: no cookies, headers, bodies, query strings, or exceptions.
    logger.info(json.dumps(record, ensure_ascii=True))


def record_request(request: Request, status: int):
    path = request.url.path
    if request.method in {"GET", "HEAD", "OPTIONS"} and path.startswith("/api/"):
        return
    if path.startswith(
        (
            "/health",
            "/api/v1/sources",
            "/api/v1/events",
            "/api/v1/dashboard",
            "/api/v1/system",
            "/api/v1/auth",
        )
    ):
        return
    route = request.scope.get("route")
    path = getattr(route, "path", "/unmatched")[:512]
    emit_activity(
        request,
        "application_error" if status >= 500 else "application_request",
        f"{request.method} {path}: HTTP {status}",
        http_status=status,
        method=request.method,
        path=path,
        level="ERROR" if status >= 500 else "INFO",
    )
