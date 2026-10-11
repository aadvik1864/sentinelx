import json
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, IPvAnyAddress, field_validator

Severity = Literal["low", "medium", "high", "critical"]
Role = Literal["ADMIN", "ANALYST", "VIEWER"]
AlertStatus = Literal["open", "acknowledged", "investigating", "resolved", "false_positive"]
IncidentStatus = Literal["open", "investigating", "contained", "resolved"]
RuleKind = Literal[
    "threshold",
    "successful_after_failures",
    "privilege_escalation",
    "port_scan",
    "http_errors",
    "suspicious_authentication",
]
Password = Annotated[str, Field(min_length=12, max_length=128)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Register(StrictModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: Password

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class Login(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    otp: str = Field(default="", max_length=64)


class MFASetup(StrictModel):
    password: str = Field(min_length=1, max_length=128)


class MFAEnable(StrictModel):
    code: str = Field(pattern=r"^\d{6}$")


class ChangePassword(StrictModel):
    current_password: str = Field(max_length=128)
    new_password: Password


class EventInput(StrictModel):
    timestamp: datetime
    source: Literal["linux", "nginx", "apache", "application", "network"]
    event_type: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    severity: Severity = "low"
    source_ip: IPvAnyAddress | None = None
    destination_ip: IPvAnyAddress | None = None
    username: str | None = Field(default=None, max_length=100)
    hostname: str = Field(min_length=1, max_length=253)
    message: str = Field(min_length=1, max_length=8000)
    metadata: dict = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("timestamp must include a UTC offset")
        value = value.astimezone(UTC)
        if (value - datetime.now(UTC)).total_seconds() > 60:
            raise ValueError("timestamp cannot be more than 60 seconds in the future")
        return value

    @field_validator("metadata")
    @classmethod
    def bounded_metadata(cls, value):
        if len(json.dumps(value)) > 16000:
            raise ValueError("metadata exceeds 16 KB")
        port = value.get("destination_port")
        if port is not None and (type(port) is not int or not 1 <= port <= 65535):
            raise ValueError("destination_port must be an integer between 1 and 65535")
        status = value.get("http_status")
        if status is not None and (type(status) is not int or not 100 <= status <= 599):
            raise ValueError("http_status must be an integer between 100 and 599")
        return value


class RawLog(StrictModel):
    source: Literal["linux", "nginx", "apache", "application"]
    line: str = Field(min_length=1, max_length=20000)
    hostname: str = Field(min_length=1, max_length=253)
    timestamp: datetime | None = None


class SourceInput(StrictModel):
    name: str = Field(min_length=2, max_length=100)
    kind: Literal["linux", "nginx", "apache", "application"]
    hostname: str = Field(min_length=1, max_length=253)
    log_path: str = Field(default="", max_length=512)


class SourcePatch(StrictModel):
    enabled: bool


class SourceRecord(StrictModel):
    record_key: str = Field(min_length=16, max_length=128, pattern=r"^[a-zA-Z0-9_:.-]+$")
    line: str = Field(min_length=1, max_length=20000)
    timestamp: datetime | None = None


class SourceHeartbeat(StrictModel):
    state: Literal["listening", "error"]
    # Codes, never arbitrary exception text or credentials supplied by a collector.
    error: Literal[
        "",
        "file_unavailable",
        "docker_unavailable",
        "record_rejected",
        "connection_failed",
        "configuration_error",
        "log_gap",
    ] = ""


class AlertPatch(StrictModel):
    status: AlertStatus


class IncidentCreate(StrictModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=8000)
    severity: Severity = "medium"
    event_ids: list[int] = Field(default_factory=list, max_length=200)
    alert_ids: list[int] = Field(default_factory=list, max_length=100)


class IncidentPatch(StrictModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    severity: Severity | None = None
    status: IncidentStatus | None = None
    assigned_to: int | None = Field(default=None, gt=0)


class NoteInput(StrictModel):
    content: str = Field(min_length=1, max_length=8000)
    kind: Literal["note", "evidence"] = "note"


class LinkEvents(StrictModel):
    event_ids: list[int] = Field(min_length=1, max_length=200)


class RuleInput(StrictModel):
    name: str = Field(min_length=3, max_length=150)
    description: str = Field(default="", max_length=2000)
    kind: RuleKind = "threshold"
    event_type: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    threshold: int = Field(default=10, ge=1, le=100000)
    window_seconds: int = Field(default=300, ge=1, le=86400)
    severity: Severity = "high"
    enabled: bool = True
    mitre_techniques: list[str] = Field(default_factory=list, max_length=20)
    config: dict = Field(default_factory=dict)

    @field_validator("mitre_techniques")
    @classmethod
    def valid_techniques(cls, value):
        import re

        if any(not re.fullmatch(r"T\d{4}(?:\.\d{3})?", item) for item in value):
            raise ValueError("Invalid ATT&CK technique ID")
        return sorted(set(value))

    @field_validator("config")
    @classmethod
    def valid_config(cls, value):
        if set(value) - {"error_ratio", "sources"}:
            raise ValueError("Supported rule configuration: error_ratio, sources")
        ratio = value.get("error_ratio", 0.3)
        if type(ratio) not in (int, float) or not 0 < ratio <= 1:
            raise ValueError("error_ratio must be between 0 and 1")
        sources = value.get("sources")
        if sources is not None and (
            not isinstance(sources, list)
            or not sources
            or len(sources) > 5
            or any(
                not isinstance(item, str)
                or item not in {"linux", "nginx", "apache", "application", "network"}
                for item in sources
            )
        ):
            raise ValueError("sources must be a non-empty list of supported log formats")
        return value


class RulePatch(RuleInput):
    name: str | None = Field(default=None, min_length=3, max_length=150)
    event_type: str | None = Field(
        default=None, min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$"
    )


class AssetInput(StrictModel):
    hostname: str = Field(min_length=1, max_length=253)
    ip_address: IPvAnyAddress
    type: Literal["server", "application", "endpoint"] = "server"
    environment: str = Field(default="lab", max_length=30)
    owner: str = Field(default="Security operations", max_length=100)
    status: Literal["active", "inactive"] = "active"


class UserPatch(StrictModel):
    role: Role


class UserAccess(StrictModel):
    disabled: bool


class AnalyzeIncident(StrictModel):
    incident_id: int = Field(gt=0)


class ExplainAlert(StrictModel):
    alert_id: int = Field(gt=0)


class Analysis(StrictModel):
    summary: str = Field(max_length=3000)
    likely_attack: str = Field(max_length=1000)
    evidence: list[str] = Field(max_length=30)
    affected_assets: list[str] = Field(max_length=30)
    mitre_techniques: list[str] = Field(max_length=20)
    confidence: Literal["low", "medium", "high"]
    recommended_investigation: list[str] = Field(max_length=20)
    recommended_containment: list[str] = Field(max_length=20)
    false_positive_indicators: list[str] = Field(max_length=20)
