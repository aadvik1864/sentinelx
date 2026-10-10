import shlex
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, select

from app.services.serialization import serialize


def require_row(db, model, row_id):
    row = db.get(model, row_id)
    if not row:
        raise HTTPException(404, "Resource not found")
    return row


def page(db, query, model, limit=50, offset=0):
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    return {
        "items": [serialize(row) for row in db.scalars(query.limit(limit).offset(offset)).all()],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def search(query, model, value, fields, text_field="message"):
    if not value:
        return query
    try:
        terms = shlex.split(value)
    except ValueError:
        raise HTTPException(422, "Search has an unclosed quote") from None
    for term in terms:
        if ":" in term:
            key, item = term.split(":", 1)
            if key not in fields:
                raise HTTPException(422, f"Unsupported search field: {key}")
            query = query.where(getattr(model, key) == item)
        else:
            query = query.where(getattr(model, text_field).contains(term, autoescape=True))
    return query


def utc_filter(value: datetime | None):
    if value is None:
        return None
    if value.tzinfo is None:
        raise HTTPException(422, "Time filters must include a UTC offset")
    return value.astimezone(UTC).replace(tzinfo=None)
