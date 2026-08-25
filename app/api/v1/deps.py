from dataclasses import dataclass, field
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.database import get_db
from app.models.outlet_membership import OutletMembership
from app.models.platform_admin import PlatformAdmin
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User

security = HTTPBearer()


@dataclass
class MembershipSummary:
    membership_id: UUID
    outlet_id: UUID
    outlet_name: str
    outlet_slug: str
    role_name: str
    active_status: bool


@dataclass
class CurrentUser:
    id: UUID
    user_type: Literal["user", "platform_admin", "platform_support"]
    outlet_id: UUID | None
    db_user: User | PlatformAdmin | None
    memberships: list[MembershipSummary] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)


def _load_user_memberships(db: Session, user_id: UUID) -> list[MembershipSummary]:
    rows = (
        db.query(OutletMembership)
        .options(joinedload(OutletMembership.outlet), joinedload(OutletMembership.role))
        .filter(OutletMembership.user_id == user_id)
        .order_by(OutletMembership.created_at.asc())
        .all()
    )
    return [
        MembershipSummary(
            membership_id=row.id,
            outlet_id=row.outlet_id,
            outlet_name=row.outlet.name,
            outlet_slug=row.outlet.slug,
            role_name=row.role.name,
            active_status=row.active_status,
        )
        for row in rows
    ]


def _resolve_membership_permissions(
    db: Session, user_id: UUID, outlet_id: UUID
) -> list[str]:
    membership = (
        db.query(OutletMembership)
        .options(
            joinedload(OutletMembership.role)
            .joinedload(Role.role_permissions)
            .joinedload(RolePermission.permission)
        )
        .filter(
            OutletMembership.user_id == user_id,
            OutletMembership.outlet_id == outlet_id,
            OutletMembership.active_status.is_(True),
        )
        .first()
    )
    if membership is None:
        return []
    return sorted(rp.permission.key for rp in membership.role.role_permissions)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[Session, Depends(get_db)],
) -> CurrentUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id: str | None = payload.get("sub")
        user_type: str | None = payload.get("user_type")
        if user_id is None or user_type is None:
            raise credentials_exception
        user_uuid = UUID(user_id)
    except (JWTError, ValueError):
        raise credentials_exception

    if user_type == "user":
        user = db.query(User).filter(User.id == user_uuid).first()
        if user is None:
            raise credentials_exception

        outlet_id_raw = payload.get("outlet_id")
        outlet_id = UUID(str(outlet_id_raw)) if outlet_id_raw else None
        memberships = _load_user_memberships(db, user.id)
        permissions: list[str] = []
        if outlet_id is not None:
            permissions = _resolve_membership_permissions(db, user.id, outlet_id)

        return CurrentUser(
            id=user.id,
            user_type="user",
            outlet_id=outlet_id,
            db_user=user,
            memberships=memberships,
            permissions=permissions,
        )

    if user_type == "platform_admin":
        user = db.query(PlatformAdmin).filter(PlatformAdmin.id == user_uuid).first()
        if user is None or not user.active_status:
            raise credentials_exception
        return CurrentUser(
            id=user.id,
            user_type="platform_admin",
            outlet_id=None,
            db_user=user,
        )

    if user_type == "platform_support":
        admin = db.query(PlatformAdmin).filter(PlatformAdmin.id == user_uuid).first()
        if admin is None:
            raise credentials_exception

        outlet_id_raw = payload.get("outlet_id")
        platform_admin_id_raw = payload.get("platform_admin_id")
        permissions = payload.get("permissions")
        if (
            outlet_id_raw is None
            or platform_admin_id_raw is None
            or not isinstance(permissions, list)
        ):
            raise credentials_exception

        try:
            outlet_id = UUID(str(outlet_id_raw))
            platform_admin_id = UUID(str(platform_admin_id_raw))
        except ValueError:
            raise credentials_exception

        if platform_admin_id != admin.id:
            raise credentials_exception

        return CurrentUser(
            id=admin.id,
            user_type="platform_support",
            outlet_id=outlet_id,
            db_user=admin,
            permissions=[str(key) for key in permissions],
        )

    raise credentials_exception


def require_platform_admin(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    if current_user.user_type != "platform_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin access required",
        )
    return current_user


def require_user(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    if current_user.user_type != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User access required",
        )
    return current_user


def require_permission(permission_key: str):
    def _check_permission(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
    ) -> CurrentUser:
        if current_user.user_type == "platform_support":
            if permission_key not in current_user.permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions",
                )
            return current_user

        if current_user.user_type == "platform_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        if current_user.user_type != "user":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        if current_user.outlet_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Outlet context required",
            )

        if permission_key not in current_user.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return current_user

    return _check_permission


def get_outlet_scope(current_user: CurrentUser) -> UUID:
    if current_user.outlet_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Outlet scope required",
        )
    return current_user.outlet_id


def require_outlet_permission(permission_key: str):
    permission_dep = require_permission(permission_key)

    def _check_outlet_scope(
        outlet_id: UUID,
        current_user: Annotated[CurrentUser, Depends(permission_dep)],
        db: Annotated[Session, Depends(get_db)],
    ) -> CurrentUser:
        if get_outlet_scope(current_user) != outlet_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Outlet access denied",
            )
        from app.services import subscription as subscription_service

        module = permission_key.split(".", 1)[0]
        subscription_service.enforce_outlet_plan_module(db, outlet_id, module)
        return current_user

    return _check_outlet_scope
