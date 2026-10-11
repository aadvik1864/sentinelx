from datetime import datetime

from sqlalchemy import inspect


def serialize(row):
    result = {}
    for column in inspect(type(row)).column_attrs:
        key = "metadata" if column.key == "details" else column.key
        if key in {"password_hash", "auth_version", "token_hash"} or key.startswith("mfa_"):
            continue
        value = getattr(row, column.key)
        if isinstance(value, datetime):
            value = value.isoformat(timespec="milliseconds") + "Z"
        result[key] = value
    if type(row).__name__ == "User":
        result["mfa_enabled"] = bool(row.mfa_secret)
    prefixes = {"Alert": "ALT", "Incident": "INC", "Event": "EVT", "DetectionRule": "RUL"}
    if type(row).__name__ in prefixes:
        result["reference"] = f"{prefixes[type(row).__name__]}-{row.id:05d}"
    return result
