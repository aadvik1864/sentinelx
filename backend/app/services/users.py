from fastapi import HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import audit, hash_password
from app.models import User
from app.schemas import Register
from app.services.serialization import serialize


def provision_viewer(db: Session, data: Register, administrator: User, request: Request):
    """Admit only an administrator-selected person; never store/audit their password."""
    user = User(
        name=data.name.strip(),
        email=str(data.email).lower(),
        password_hash=hash_password(data.password),
        role="VIEWER",
    )
    db.add(user)
    try:
        db.flush()
        audit(db, administrator, "CREATE_USER", "user", user.id, request, {"role": "VIEWER"})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists") from None
    return serialize(user)
