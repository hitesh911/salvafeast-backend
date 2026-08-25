from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.models.outlet_membership import OutletMembership
from app.services.roles import get_system_role_by_name


def transfer_ownership(
    db: Session,
    outlet_id: UUID,
    *,
    new_owner_membership_id: UUID,
    demote_previous_to: str = "Manager",
) -> dict[str, UUID]:
    owner_role = get_system_role_by_name(db, "Owner")
    demote_role = get_system_role_by_name(db, demote_previous_to)
    if owner_role is None or demote_role is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="System roles not configured. Run the seed script.",
        )

    current_owner = (
        db.query(OutletMembership)
        .options(joinedload(OutletMembership.role))
        .filter(
            OutletMembership.outlet_id == outlet_id,
            OutletMembership.role_id == owner_role.id,
        )
        .first()
    )
    if current_owner is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No current owner found for this outlet",
        )

    new_owner = (
        db.query(OutletMembership)
        .options(joinedload(OutletMembership.role))
        .filter(
            OutletMembership.id == new_owner_membership_id,
            OutletMembership.outlet_id == outlet_id,
        )
        .first()
    )
    if new_owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff not found")
    if not new_owner.active_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot transfer ownership to an inactive user",
        )
    if new_owner.id == current_owner.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This user is already the owner",
        )

    previous_owner_id = current_owner.id
    current_owner.role_id = demote_role.id
    new_owner.role_id = owner_role.id

    db.commit()
    return {
        "previous_owner_id": previous_owner_id,
        "new_owner_id": new_owner.id,
    }
