from uuid import UUID

from sqlalchemy.orm import Session

from app.core.phone import normalize_indian_phone
from app.models.user import User


def find_or_create_user(db: Session, phone: str, *, name: str | None = None) -> User:
    normalized = normalize_indian_phone(phone)
    user = db.query(User).filter(User.phone == normalized).first()
    if user is None:
        user = User(phone=normalized, name=name.strip() if name else None)
        db.add(user)
        db.flush()
    elif name and not user.name:
        user.name = name.strip()
    return user


def get_user_by_id(db: Session, user_id: UUID) -> User | None:
    return db.query(User).filter(User.id == user_id).first()
