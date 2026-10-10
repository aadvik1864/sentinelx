from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.common import require_row
from app.core.database import get_db
from app.core.security import admin_only, audit, read_security
from app.models import DetectionRule, User
from app.schemas import RuleInput, RulePatch
from app.services.serialization import serialize

router = APIRouter(prefix="/rules", tags=["Detection rules"])


def commit_rule(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Rule names must be unique") from None


@router.get("")
def list_rules(user: User = Depends(read_security), db: Session = Depends(get_db)):
    return {
        "items": [
            serialize(row) for row in db.scalars(select(DetectionRule).order_by(DetectionRule.id))
        ]
    }


@router.post("", status_code=201)
def create_rule(
    data: RuleInput,
    request: Request,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    if db.scalar(select(DetectionRule.id).where(DetectionRule.name == data.name)):
        raise HTTPException(409, "Rule names must be unique")
    rule = DetectionRule(**data.model_dump())
    db.add(rule)
    db.flush()
    audit(db, user, "CREATE_RULE", "rule", rule.id, request)
    commit_rule(db)
    return serialize(rule)


@router.get("/{rule_id}")
def rule_detail(rule_id: int, user: User = Depends(read_security), db: Session = Depends(get_db)):
    return serialize(require_row(db, DetectionRule, rule_id))


@router.patch("/{rule_id}")
def update_rule(
    rule_id: int,
    data: RulePatch,
    request: Request,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    rule = require_row(db, DetectionRule, rule_id)
    # RuleInput defaults must not silently reset unspecified fields on PATCH.
    values = data.model_dump(exclude_unset=True)
    if any(value is None for value in values.values()):
        raise HTTPException(422, "Rule fields cannot be null")
    before = {key: getattr(rule, key) for key in values}
    for key, value in values.items():
        setattr(rule, key, value)
    audit(db, user, "UPDATE_RULE", "rule", rule_id, request, {"before": before, "after": values})
    commit_rule(db)
    return serialize(rule)


@router.delete("/{rule_id}", status_code=204)
def delete_rule(
    rule_id: int, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)
):
    rule = require_row(db, DetectionRule, rule_id)
    audit(db, user, "DELETE_RULE", "rule", rule_id, request, {"name": rule.name})
    db.delete(rule)
    db.commit()
