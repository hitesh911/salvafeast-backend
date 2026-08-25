from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    access_token_expires_in_seconds,
    create_access_token,
    create_support_access_token,
    create_user_token,
    hash_refresh_token,
    verify_refresh_token,
)
from app.models.outlet import Outlet
from app.models.outlet_membership import OutletMembership
from app.models.permission import Permission
from app.models.platform_admin import PlatformAdmin
from app.models.refresh_token import RefreshToken
from app.models.user import User

SessionKind = Literal["user", "platform_admin", "platform_support"]


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    refresh_expires_at: datetime


def _refresh_expires_at(now: datetime | None = None) -> datetime:
    base = now or datetime.now(timezone.utc)
    return base + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)


def _generate_plain_refresh_token(row_id: UUID) -> str:
    return f"{row_id}.{secrets.token_urlsafe(32)}"


def _parse_refresh_token_id(plain_token: str) -> UUID | None:
    if "." not in plain_token:
        return None
    prefix = plain_token.split(".", 1)[0]
    try:
        return UUID(prefix)
    except ValueError:
        return None


def _find_active_refresh_row(db: Session, plain_token: str) -> RefreshToken | None:
    row_id = _parse_refresh_token_id(plain_token)
    if row_id is None:
        return None
    row = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.id == row_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )
    if row is None:
        return None
    if not verify_refresh_token(plain_token, row.token_hash):
        return None
    return row


def _validate_user_session(db: Session, user_id: UUID, outlet_id: UUID | None) -> None:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    if outlet_id is None:
        return
    membership = (
        db.query(OutletMembership)
        .filter(
            OutletMembership.user_id == user_id,
            OutletMembership.outlet_id == outlet_id,
            OutletMembership.active_status.is_(True),
        )
        .first()
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )


def _validate_platform_admin_session(db: Session, admin_id: UUID) -> PlatformAdmin:
    admin = db.query(PlatformAdmin).filter(PlatformAdmin.id == admin_id).first()
    if admin is None or not admin.active_status:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    return admin


def _validate_support_session(
    db: Session, admin_id: UUID, outlet_id: UUID | None, meta: dict[str, Any] | None
) -> tuple[list[str], UUID]:
    admin = _validate_platform_admin_session(db, admin_id)
    if outlet_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    outlet = db.query(Outlet).filter(Outlet.id == outlet_id).first()
    if outlet is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    permissions: list[str] = []
    if meta and isinstance(meta.get("permissions"), list):
        permissions = [str(key) for key in meta["permissions"]]
    else:
        permissions = sorted(
            key
            for (key,) in db.query(Permission.key).filter(Permission.key.like("%.view")).all()
        )

    platform_admin_id_raw = meta.get("platform_admin_id") if meta else None
    if platform_admin_id_raw is not None:
        try:
            if UUID(str(platform_admin_id_raw)) != admin.id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid refresh token",
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

    return permissions, outlet.id


def _create_access_for_row(db: Session, row: RefreshToken) -> str:
    if row.session_kind == "user":
        _validate_user_session(db, row.subject_id, row.outlet_id)
        outlet_id = str(row.outlet_id) if row.outlet_id else None
        return create_user_token(str(row.subject_id), outlet_id)

    if row.session_kind == "platform_admin":
        _validate_platform_admin_session(db, row.subject_id)
        return create_access_token(
            {"sub": str(row.subject_id), "user_type": "platform_admin"}
        )

    if row.session_kind == "platform_support":
        permissions, outlet_id = _validate_support_session(
            db, row.subject_id, row.outlet_id, row.session_meta
        )
        meta = row.session_meta or {}
        token, _ = create_support_access_token(
            {
                "sub": str(row.subject_id),
                "user_type": "platform_support",
                "platform_admin_id": str(
                    meta.get("platform_admin_id", row.subject_id)
                ),
                "outlet_id": str(outlet_id),
                "permissions": permissions,
            }
        )
        return token

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
    )


def _persist_refresh_row(
    db: Session,
    *,
    session_kind: SessionKind,
    subject_id: UUID,
    outlet_id: UUID | None,
    session_meta: dict[str, Any] | None,
    expires_at: datetime,
) -> tuple[RefreshToken, str]:
    row = RefreshToken(
        session_kind=session_kind,
        subject_id=subject_id,
        outlet_id=outlet_id,
        session_meta=session_meta,
        token_hash="",
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()
    plain_token = _generate_plain_refresh_token(row.id)
    row.token_hash = hash_refresh_token(plain_token)
    db.flush()
    return row, plain_token


def issue_tokens(
    db: Session,
    *,
    session_kind: SessionKind,
    subject_id: UUID,
    outlet_id: UUID | None = None,
    session_meta: dict[str, Any] | None = None,
) -> TokenPair:
    if session_kind == "user":
        _validate_user_session(db, subject_id, outlet_id)
    elif session_kind == "platform_admin":
        _validate_platform_admin_session(db, subject_id)
    elif session_kind == "platform_support":
        _validate_support_session(db, subject_id, outlet_id, session_meta)

    plain_refresh: str
    refresh_expires_at = _refresh_expires_at()
    row, plain_refresh = _persist_refresh_row(
        db,
        session_kind=session_kind,
        subject_id=subject_id,
        outlet_id=outlet_id,
        session_meta=session_meta,
        expires_at=refresh_expires_at,
    )
    db.commit()
    db.refresh(row)

    access_token = _create_access_for_row(db, row)
    return TokenPair(
        access_token=access_token,
        refresh_token=plain_refresh,
        expires_in=access_token_expires_in_seconds(),
        refresh_expires_at=refresh_expires_at,
    )


def refresh_session(db: Session, plain_refresh_token: str) -> TokenPair:
    row = _find_active_refresh_row(db, plain_refresh_token)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    now = datetime.now(timezone.utc)
    row.last_used_at = now
    row.revoked_at = now

    new_plain: str
    new_expires_at = _refresh_expires_at(now)
    new_row, new_plain = _persist_refresh_row(
        db,
        session_kind=row.session_kind,  # type: ignore[arg-type]
        subject_id=row.subject_id,
        outlet_id=row.outlet_id,
        session_meta=row.session_meta,
        expires_at=new_expires_at,
    )
    row.replaced_by_id = new_row.id
    db.commit()
    db.refresh(new_row)

    access_token = _create_access_for_row(db, new_row)
    return TokenPair(
        access_token=access_token,
        refresh_token=new_plain,
        expires_in=access_token_expires_in_seconds(),
        refresh_expires_at=new_expires_at,
    )


def revoke_refresh_token(db: Session, plain_refresh_token: str) -> None:
    row = _find_active_refresh_row(db, plain_refresh_token)
    if row is None:
        return
    row.revoked_at = datetime.now(timezone.utc)
    db.commit()
