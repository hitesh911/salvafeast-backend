from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.outlet_membership import OutletMembership
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission

RESERVED_ROLE_NAMES = {"Owner"}


def list_permissions(db: Session) -> list[Permission]:
    return db.query(Permission).order_by(Permission.module.asc(), Permission.key.asc()).all()


def list_roles(db: Session, outlet_id: UUID) -> list[Role]:
    return (
        db.query(Role)
        .options(joinedload(Role.role_permissions).joinedload(RolePermission.permission))
        .filter(
            or_(
                (Role.outlet_id.is_(None)) & (Role.is_system_default.is_(True)),
                Role.outlet_id == outlet_id,
            )
        )
        .order_by(Role.is_system_default.desc(), Role.name.asc())
        .all()
    )


def _get_role_for_outlet(db: Session, outlet_id: UUID, role_id: UUID) -> Role:
    role = (
        db.query(Role)
        .options(joinedload(Role.role_permissions).joinedload(RolePermission.permission))
        .filter(Role.id == role_id)
        .first()
    )
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system_default:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System roles cannot be modified",
        )
    if role.outlet_id != outlet_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return role


def _validate_permission_ids(db: Session, permission_ids: list[UUID]) -> list[Permission]:
    if not permission_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one permission is required",
        )
    permissions = db.query(Permission).filter(Permission.id.in_(permission_ids)).all()
    if len(permissions) != len(set(permission_ids)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid permission")
    return permissions


def _role_name_taken(db: Session, outlet_id: UUID, name: str, exclude_id: UUID | None = None) -> bool:
    query = db.query(Role).filter(
        or_(
            (Role.outlet_id.is_(None)) & (Role.is_system_default.is_(True)),
            Role.outlet_id == outlet_id,
        ),
        Role.name.ilike(name.strip()),
    )
    if exclude_id is not None:
        query = query.filter(Role.id != exclude_id)
    return query.first() is not None


def create_custom_role(
    db: Session,
    outlet_id: UUID,
    *,
    name: str,
    permission_ids: list[UUID],
) -> Role:
    trimmed = name.strip()
    if not trimmed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role name is required")
    if trimmed in RESERVED_ROLE_NAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This role name is reserved",
        )
    if _role_name_taken(db, outlet_id, trimmed):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A role with this name already exists",
        )

    permissions = _validate_permission_ids(db, permission_ids)
    role = Role(
        outlet_id=outlet_id,
        name=trimmed,
        is_system_default=False,
    )
    db.add(role)
    db.flush()
    for perm in permissions:
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.commit()
    return _get_role_for_outlet(db, outlet_id, role.id)


def update_custom_role(
    db: Session,
    outlet_id: UUID,
    role_id: UUID,
    *,
    name: str | None = None,
    permission_ids: list[UUID] | None = None,
) -> Role:
    role = _get_role_for_outlet(db, outlet_id, role_id)

    if name is not None:
        trimmed = name.strip()
        if not trimmed:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role name is required")
        if trimmed in RESERVED_ROLE_NAMES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This role name is reserved",
            )
        if _role_name_taken(db, outlet_id, trimmed, exclude_id=role.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A role with this name already exists",
            )
        role.name = trimmed

    if permission_ids is not None:
        permissions = _validate_permission_ids(db, permission_ids)
        db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()
        for perm in permissions:
            db.add(RolePermission(role_id=role.id, permission_id=perm.id))

    db.commit()
    return _get_role_for_outlet(db, outlet_id, role.id)


def delete_custom_role(db: Session, outlet_id: UUID, role_id: UUID) -> None:
    role = _get_role_for_outlet(db, outlet_id, role_id)
    assigned = (
        db.query(OutletMembership)
        .filter(OutletMembership.outlet_id == outlet_id, OutletMembership.role_id == role.id)
        .count()
    )
    if assigned > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a role that is assigned to staff",
        )
    db.delete(role)
    db.commit()


def get_system_role_by_name(db: Session, name: str) -> Role | None:
    return (
        db.query(Role)
        .filter(
            Role.outlet_id.is_(None),
            Role.is_system_default.is_(True),
            Role.name == name,
        )
        .first()
    )
