from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.models.outlet_membership import OutletMembership
from app.models.user import User
from app.schemas.auth import MembershipSummaryResponse
from app.schemas.user_profile import UserProfileResponse, UserProfileUpdate


def _membership_summaries(db: Session, user_id: UUID) -> list[MembershipSummaryResponse]:
    memberships = (
        db.query(OutletMembership)
        .options(joinedload(OutletMembership.outlet), joinedload(OutletMembership.role))
        .filter(OutletMembership.user_id == user_id)
        .order_by(OutletMembership.created_at.asc())
        .all()
    )
    return [
        MembershipSummaryResponse(
            membership_id=m.id,
            outlet_id=m.outlet_id,
            outlet_name=m.outlet.name,
            outlet_slug=m.outlet.slug,
            role_name=m.role.name,
            active_status=m.active_status,
        )
        for m in memberships
    ]


def dietary_list(user: User) -> list[str]:
    prefs = user.dietary_preferences if isinstance(user.dietary_preferences, list) else []
    return [str(p) for p in prefs]


def build_user_profile_response(db: Session, user: User) -> UserProfileResponse:
    return UserProfileResponse(
        id=user.id,
        phone=user.phone,
        name=user.name,
        email=user.email,
        avatar_url=user.avatar_url,
        date_of_birth=user.date_of_birth,
        gender=user.gender,
        dietary_preferences=dietary_list(user),
        profile_completed_at=user.profile_completed_at,
        memberships=_membership_summaries(db, user.id),
    )


def update_user_profile(
    db: Session, user: User, payload: UserProfileUpdate
) -> User:
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(user, key, value)

    if user.name and user.name.strip() and user.profile_completed_at is None:
        user.profile_completed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(user)
    return user
