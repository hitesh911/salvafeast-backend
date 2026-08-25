from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from app.api.v1.deps import CurrentUser, require_outlet_permission
from app.db.database import get_db
from app.models.outlet import Outlet
from app.models.outlet_membership import OutletMembership
from app.models.role import Role
from app.schemas.outlet_settings import (
    OutletInvoicingSettingsResponse,
    OutletInvoicingSettingsUpdate,
    OutletPermissionItem,
    OutletPreferencesResponse,
    OutletPreferencesUpdate,
    OutletProfileSettingsResponse,
    OutletProfileSettingsUpdate,
    OutletRoleCreate,
    OutletRoleItem,
    OutletRoleUpdate,
    OutletStaffCreate,
    OutletStaffItem,
    OutletStaffUpdate,
    OwnershipTransferRequest,
    OwnershipTransferResponse,
)
from app.services import ownership as ownership_service
from app.services import roles as roles_service
from app.services import staff as staff_service
from app.services.outlet_address import apply_structured_address
from app.services.outlet_media import store_outlet_cover, store_outlet_logo
from app.services.outlet_profile import build_outlet_profile_response

router = APIRouter(prefix="/outlets/{outlet_id}", tags=["outlet-settings"])


def _get_outlet(db: Session, outlet_id: UUID) -> Outlet:
    outlet = db.query(Outlet).filter(Outlet.id == outlet_id).first()
    if outlet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outlet not found")
    return outlet


def _staff_to_item(membership: OutletMembership) -> OutletStaffItem:
    user = membership.user
    return OutletStaffItem(
        id=str(membership.id),
        user_id=str(user.id),
        outlet_id=str(membership.outlet_id),
        name=user.name or "",
        phone=user.phone,
        email=user.email,
        role_id=str(membership.role_id),
        role_name=membership.role.name if membership.role else "",
        active_status=membership.active_status,
        last_login=user.last_login.isoformat() if user.last_login else None,
        created_at=membership.created_at.isoformat(),
    )


def _role_to_item(role: Role) -> OutletRoleItem:
    return OutletRoleItem(
        id=str(role.id),
        name=role.name,
        is_system_default=role.is_system_default,
        permission_keys=sorted(rp.permission.key for rp in role.role_permissions),
    )


def _require_owner(current: CurrentUser, db: Session) -> None:
    if current.user_type != "user" or current.outlet_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Outlet user required")
    membership = (
        db.query(OutletMembership)
        .options(joinedload(OutletMembership.role))
        .filter(
            OutletMembership.user_id == current.id,
            OutletMembership.outlet_id == current.outlet_id,
            OutletMembership.active_status.is_(True),
        )
        .first()
    )
    if membership is None or membership.role.name != "Owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the outlet owner can change this setting",
        )


@router.get("/settings/profile", response_model=OutletProfileSettingsResponse)
def get_profile_settings(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("staff.view")),
):
    outlet = _get_outlet(db, outlet_id)
    return build_outlet_profile_response(outlet)


@router.patch("/settings/profile", response_model=OutletProfileSettingsResponse)
def update_profile_settings(
    outlet_id: UUID,
    payload: OutletProfileSettingsUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("staff.edit")),
):
    outlet = _get_outlet(db, outlet_id)
    apply_structured_address(outlet, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(outlet)
    return build_outlet_profile_response(outlet)


@router.post("/settings/profile/logo", response_model=OutletProfileSettingsResponse)
async def upload_profile_logo(
    outlet_id: UUID,
    logo: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("staff.edit")),
):
    outlet = _get_outlet(db, outlet_id)
    outlet.logo_url = await store_outlet_logo(outlet_id, logo)
    db.commit()
    db.refresh(outlet)
    return build_outlet_profile_response(outlet)


@router.delete("/settings/profile/logo", response_model=OutletProfileSettingsResponse)
def delete_profile_logo(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("staff.edit")),
):
    outlet = _get_outlet(db, outlet_id)
    outlet.logo_url = None
    db.commit()
    db.refresh(outlet)
    return build_outlet_profile_response(outlet)


@router.post("/settings/profile/cover", response_model=OutletProfileSettingsResponse)
async def upload_profile_cover(
    outlet_id: UUID,
    cover: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("staff.edit")),
):
    outlet = _get_outlet(db, outlet_id)
    outlet.cover_image_url = await store_outlet_cover(outlet_id, cover)
    db.commit()
    db.refresh(outlet)
    return build_outlet_profile_response(outlet)


@router.delete("/settings/profile/cover", response_model=OutletProfileSettingsResponse)
def delete_profile_cover(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("staff.edit")),
):
    outlet = _get_outlet(db, outlet_id)
    outlet.cover_image_url = None
    db.commit()
    db.refresh(outlet)
    return build_outlet_profile_response(outlet)


@router.get("/settings/invoicing", response_model=OutletInvoicingSettingsResponse)
def get_invoicing_settings(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("billing.view")),
):
    outlet = _get_outlet(db, outlet_id)
    return OutletInvoicingSettingsResponse(
        gst_rate_percent=outlet.gst_rate_percent,
        invoice_prefix=outlet.invoice_prefix,
    )


@router.patch("/settings/invoicing", response_model=OutletInvoicingSettingsResponse)
def update_invoicing_settings(
    outlet_id: UUID,
    payload: OutletInvoicingSettingsUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("billing.edit")),
):
    outlet = _get_outlet(db, outlet_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(outlet, key, value)
    db.commit()
    db.refresh(outlet)
    return OutletInvoicingSettingsResponse(
        gst_rate_percent=outlet.gst_rate_percent,
        invoice_prefix=outlet.invoice_prefix,
    )


@router.get("/settings/preferences", response_model=OutletPreferencesResponse)
def get_preferences(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("staff.view")),
):
    outlet = _get_outlet(db, outlet_id)
    return OutletPreferencesResponse(
        require_customer_login=outlet.require_customer_login,
        require_prepaid=outlet.require_prepaid,
    )


@router.patch("/settings/preferences", response_model=OutletPreferencesResponse)
def update_preferences(
    outlet_id: UUID,
    payload: OutletPreferencesUpdate,
    db: Session = Depends(get_db),
    current=Depends(require_outlet_permission("staff.edit")),
):
    _require_owner(current, db)
    outlet = _get_outlet(db, outlet_id)
    if payload.require_customer_login is not None:
        outlet.require_customer_login = payload.require_customer_login
    if payload.require_prepaid is not None:
        outlet.require_prepaid = payload.require_prepaid
    db.commit()
    db.refresh(outlet)
    return OutletPreferencesResponse(
        require_customer_login=outlet.require_customer_login,
        require_prepaid=outlet.require_prepaid,
    )


@router.get("/permissions", response_model=list[OutletPermissionItem])
def list_permissions(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("staff.view")),
):
    _get_outlet(db, outlet_id)
    permissions = roles_service.list_permissions(db)
    return [
        OutletPermissionItem(
            id=str(p.id),
            key=p.key,
            description=p.description,
            module=p.module,
        )
        for p in permissions
    ]


@router.get("/roles", response_model=list[OutletRoleItem])
def list_outlet_roles(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("staff.view")),
):
    _get_outlet(db, outlet_id)
    roles = roles_service.list_roles(db, outlet_id)
    return [_role_to_item(r) for r in roles]


@router.post("/roles", response_model=OutletRoleItem, status_code=status.HTTP_201_CREATED)
def create_outlet_role(
    outlet_id: UUID,
    payload: OutletRoleCreate,
    db: Session = Depends(get_db),
    current=Depends(require_outlet_permission("staff.edit")),
):
    _require_owner(current, db)
    _get_outlet(db, outlet_id)
    role = roles_service.create_custom_role(
        db,
        outlet_id,
        name=payload.name,
        permission_ids=[UUID(pid) for pid in payload.permission_ids],
    )
    return _role_to_item(role)


@router.patch("/roles/{role_id}", response_model=OutletRoleItem)
def update_outlet_role(
    outlet_id: UUID,
    role_id: UUID,
    payload: OutletRoleUpdate,
    db: Session = Depends(get_db),
    current=Depends(require_outlet_permission("staff.edit")),
):
    _require_owner(current, db)
    _get_outlet(db, outlet_id)
    role = roles_service.update_custom_role(
        db,
        outlet_id,
        role_id,
        name=payload.name,
        permission_ids=[UUID(pid) for pid in payload.permission_ids]
        if payload.permission_ids is not None
        else None,
    )
    return _role_to_item(role)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_outlet_role(
    outlet_id: UUID,
    role_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(require_outlet_permission("staff.edit")),
):
    _require_owner(current, db)
    _get_outlet(db, outlet_id)
    roles_service.delete_custom_role(db, outlet_id, role_id)


@router.get("/staff", response_model=list[OutletStaffItem])
def list_staff(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("staff.view")),
):
    _get_outlet(db, outlet_id)
    users = staff_service.list_staff(db, outlet_id)
    return [_staff_to_item(u) for u in users]


@router.post("/staff", response_model=OutletStaffItem, status_code=status.HTTP_201_CREATED)
def create_staff(
    outlet_id: UUID,
    payload: OutletStaffCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("staff.edit")),
):
    _get_outlet(db, outlet_id)
    user = staff_service.create_staff(
        db,
        outlet_id,
        name=payload.name,
        phone=payload.phone,
        role_id=UUID(payload.role_id),
        email=payload.email,
    )
    return _staff_to_item(user)


def _actor_membership_id(
    db: Session, current: CurrentUser, outlet_id: UUID
) -> UUID | None:
    if current.user_type != "user":
        return None
    membership = (
        db.query(OutletMembership)
        .filter(
            OutletMembership.user_id == current.id,
            OutletMembership.outlet_id == outlet_id,
        )
        .first()
    )
    return membership.id if membership else None


@router.patch("/staff/{membership_id}", response_model=OutletStaffItem)
def update_staff(
    outlet_id: UUID,
    membership_id: UUID,
    payload: OutletStaffUpdate,
    db: Session = Depends(get_db),
    current=Depends(require_outlet_permission("staff.edit")),
):
    membership = staff_service.update_staff(
        db,
        outlet_id,
        membership_id,
        name=payload.name,
        email=payload.email,
        active_status=payload.active_status,
        role_id=UUID(payload.role_id) if payload.role_id is not None else None,
        actor_membership_id=_actor_membership_id(db, current, outlet_id),
        is_platform=False,
    )
    return _staff_to_item(membership)


@router.post("/transfer-ownership", response_model=OwnershipTransferResponse)
def transfer_ownership(
    outlet_id: UUID,
    payload: OwnershipTransferRequest,
    db: Session = Depends(get_db),
    current=Depends(require_outlet_permission("staff.edit")),
):
    _require_owner(current, db)
    _get_outlet(db, outlet_id)
    result = ownership_service.transfer_ownership(
        db,
        outlet_id,
        new_owner_membership_id=UUID(payload.new_owner_user_id),
        demote_previous_to=payload.demote_previous_to,
    )
    return OwnershipTransferResponse(
        previous_owner_id=str(result["previous_owner_id"]),
        new_owner_id=str(result["new_owner_id"]),
    )
