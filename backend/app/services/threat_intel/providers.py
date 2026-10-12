import ipaddress
import re
from datetime import timedelta
from typing import Protocol

import httpx
from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import get_settings
from app.models import IOC, utcnow


class ThreatIntelProvider(Protocol):
    def lookup(self, kind: str, value: str) -> dict: ...


def validate_indicator(kind: str, value: str) -> str:
    if kind == "ip":
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            raise HTTPException(422, "Enter a valid IPv4 or IPv6 address") from None
    if kind == "domain":
        try:
            domain = value.rstrip(".").encode("idna").decode().lower()
        except UnicodeError:
            raise HTTPException(422, "Invalid domain") from None
        if len(domain) > 253 or not re.fullmatch(
            r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", domain
        ):
            raise HTTPException(422, "Enter a domain, not a URL")
        return domain
    if kind == "hash" and re.fullmatch(
        r"(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", value
    ):
        return value.lower()
    raise HTTPException(422, "Enter a valid MD5, SHA-1, or SHA-256 hash")


class LocalContextProvider:
    def lookup(self, kind: str, value: str) -> dict:
        metadata = {
            "notice": "No reputation provider is configured for this indicator. Unknown does not mean safe."
        }
        if kind == "ip":
            address = ipaddress.ip_address(value)
            metadata.update(
                is_global=address.is_global,
                is_private=address.is_private,
                notice="Non-public address. External reputation lookup skipped."
                if not address.is_global
                else metadata["notice"],
            )
        return {
            "reputation": "unknown",
            "confidence": None,
            "source": "local-context",
            "metadata": metadata,
        }


class AbuseIPDBProvider:
    def lookup(self, kind: str, value: str) -> dict:
        if kind != "ip" or not ipaddress.ip_address(value).is_global:
            return LocalContextProvider().lookup(kind, value)
        try:
            settings = get_settings()
            with httpx.Client(
                timeout=10,
                follow_redirects=False,
                trust_env=False,
                **({"proxy": settings.egress_proxy_url} if settings.egress_proxy_url else {}),
            ) as client:
                response = client.get(
                    "https://api.abuseipdb.com/api/v2/check",
                    params={"ipAddress": value, "maxAgeInDays": 90},
                    headers={"Key": get_settings().abuseipdb_api_key, "Accept": "application/json"},
                )
                response.raise_for_status()
                data = response.json()["data"]
                score = int(data["abuseConfidenceScore"])
                if not 0 <= score <= 100:
                    raise ValueError("Invalid score")
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            raise HTTPException(
                502, "Threat intelligence provider unavailable. Try again later."
            ) from None
        return {
            "reputation": "malicious"
            if score >= 75
            else "suspicious"
            if score >= 25
            else "no_known_reports",
            "confidence": score,
            "source": "AbuseIPDB",
            "metadata": {
                "country": data.get("countryCode"),
                "organization": data.get("isp"),
                "total_reports": data.get("totalReports"),
                "last_reported_at": data.get("lastReportedAt"),
                "notice": "Provider reputation is not proof of compromise.",
            },
        }


def lookup(db, kind: str, value: str):
    value = validate_indicator(kind, value)
    row = db.scalar(select(IOC).where(IOC.type == kind, IOC.value == value))
    if row and row.last_seen > utcnow() - timedelta(hours=6):
        return row
    provider = AbuseIPDBProvider() if get_settings().abuseipdb_api_key else LocalContextProvider()
    result = provider.lookup(kind, value)
    if not row:
        row = IOC(type=kind, value=value, reputation=result["reputation"], source=result["source"])
        db.add(row)
    row.reputation, row.confidence, row.source = (
        result["reputation"],
        result["confidence"],
        result["source"],
    )
    row.details = result["metadata"]
    row.last_seen = utcnow()
    db.flush()
    return row
