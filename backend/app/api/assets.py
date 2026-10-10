from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.common import require_row
from app.core.database import get_db
from app.core.security import admin_only, audit, read_security
from app.models import Asset, User
from app.schemas import AssetInput
from app.services.serialization import serialize

router = APIRouter(prefix="/assets", tags=["Assets"])


@router.get("")
def list_assets(user: User = Depends(read_security), db: Session = Depends(get_db)):
    return {"items": [serialize(row) for row in db.scalars(select(Asset).order_by(Asset.hostname))]}


def save_asset(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An asset with this hostname already exists") from None


@router.post("", status_code=201)
def create_asset(
    data: AssetInput,
    request: Request,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    row = Asset(**data.model_dump(exclude={"ip_address"}), ip_address=str(data.ip_address))
    db.add(row)
    # Audit and insert are committed atomically; audit identifies the supplied hostname.
    audit(db, user, "CREATE_ASSET", "asset", data.hostname, request)
    save_asset(db)
    return serialize(row)


@router.patch("/{asset_id}")
def update_asset(
    asset_id: int,
    data: AssetInput,
    request: Request,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    row = require_row(db, Asset, asset_id)
    for key, value in data.model_dump().items():
        setattr(row, key, str(value) if key == "ip_address" else value)
    audit(db, user, "UPDATE_ASSET", "asset", asset_id, request)
    save_asset(db)
    return serialize(row)
