from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.phone import normalize_indian_phone
from app.models.outlet_membership import OutletMembership
from app.models.role import Role
from app.services.users import find_or_create_user


def _load_staff_membership(
    db: Session, outlet_id: UUID, membership_id: UUID
) -> OutletMembership:
    membership = (
        db.query(OutletMembership)
        .options(
            joinedload(OutletMembership.user),
            joinedload(OutletMembership.role),
        )
        .filter(OutletMembership.id == membership_id, OutletMembership.outlet_id == outlet_id)
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff not found")
    return membership


def _validate_assignable_role(db: Session, role_id: UUID, outlet_id: UUID) -> Role:
    role = db.query(Role).filter(Role.id == role_id).first()
    if role is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
    if role.name == "Owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot assign Owner role directly; use transfer ownership",
        )
    if not role.is_system_default and role.outlet_id != outlet_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
    return role


def list_staff(db: Session, outlet_id: UUID) -> list[OutletMembership]:
    return (
        db.query(OutletMembership)
        .options(joinedload(OutletMembership.user), joinedload(OutletMembership.role))
        .filter(OutletMembership.outlet_id == outlet_id)
        .order_by(OutletMembership.created_at.asc())
        .all()
    )


def create_staff(
    db: Session,
    outlet_id: UUID,
    *,
    name: str,
    phone: str,
    role_id: UUID,
    email: str | None = None,
) -> OutletMembership:
    from app.services import subscription as subscription_service

    subscription_service.enforce_staff_limit(db, outlet_id)
    normalized_phone = normalize_indian_phone(phone)
    role = _validate_assignable_role(db, role_id, outlet_id)

    user = find_or_create_user(db, normalized_phone, name=name.strip())
    if email is not None:
        cleaned = email.strip()
        user.email = cleaned or None
    existing = (
        db.query(OutletMembership)
        .filter(
            OutletMembership.user_id == user.id,
            OutletMembership.outlet_id == outlet_id,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already staff at this outlet",
        )

    membership = OutletMembership(
        user_id=user.id,
        outlet_id=outlet_id,
        role_id=role.id,
    )
    db.add(membership)
    db.commit()
    return _load_staff_membership(db, outlet_id, membership.id)


def update_staff(
    db: Session,
    outlet_id: UUID,
    membership_id: UUID,
    *,
    name: str | None = None,
    email: str | None = None,
    active_status: bool | None = None,
    role_id: UUID | None = None,
    actor_membership_id: UUID | None = None,
    is_platform: bool = False,
) -> OutletMembership:
    membership = _load_staff_membership(db, outlet_id, membership_id)

    if not is_platform and actor_membership_id is not None:
        if actor_membership_id == membership.id:
            if active_status is False or role_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You cannot deactivate or reassign yourself",
                )

    if membership.role and membership.role.name == "Owner":
        if active_status is False or (role_id is not None and role_id != membership.role_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate or reassign the outlet owner; use transfer ownership",
            )

    if name is not None:
        membership.user.name = name.strip()
    if email is not None:
        cleaned = email.strip()
        membership.user.email = cleaned or None
    if active_status is not None:
        membership.active_status = active_status
    if role_id is not None:
        role = _validate_assignable_role(db, role_id, outlet_id)
        membership.role_id = role.id

    db.commit()
    return _load_staff_membership(db, outlet_id, membership.id)
