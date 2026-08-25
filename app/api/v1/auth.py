from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from app.api.v1.deps import CurrentUser, get_current_user, require_user
from app.db.database import get_db
from app.models.outlet import Outlet
from app.models.outlet_membership import OutletMembership
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User
from app.schemas.auth import (
    AuthMeResponse,
    LogoutRequest,
    MembershipSummaryResponse,
    OtpRequest,
    OtpRequestResponse,
    OtpVerifyRequest,
    RefreshRequest,
    SelectOutletRequest,
    TokenResponse,
)
from app.schemas.user_profile import UserProfileResponse, UserProfileUpdate
from app.services.otp import (
    OTP_SUCCESS_MESSAGE,
    assert_otp_rate_limit,
    send_otp,
    verify_otp_for_purpose,
)
from app.services.outlet_media import store_user_avatar
from app.services.refresh_tokens import issue_tokens, refresh_session, revoke_refresh_token
from app.services.user_profile import (
    build_user_profile_response,
    dietary_list,
    update_user_profile,
)
from app.services.users import find_or_create_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _active_memberships(db: Session, user_id) -> list[OutletMembership]:
    return (
        db.query(OutletMembership)
        .options(joinedload(OutletMembership.outlet), joinedload(OutletMembership.role))
        .filter(
            OutletMembership.user_id == user_id,
            OutletMembership.active_status.is_(True),
        )
        .order_by(OutletMembership.created_at.asc())
        .all()
    )


def _membership_summaries(memberships: list[OutletMembership]) -> list[MembershipSummaryResponse]:
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


def _resolve_outlet_token(db: Session, user: User) -> tuple[str | None, OutletMembership | None]:
    active = _active_memberships(db, user.id)
    if len(active) == 1:
        return str(active[0].outlet_id), active[0]
    return None, None


@router.get("/me", response_model=AuthMeResponse)
def get_me(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.user_type == "platform_support":
        if current_user.outlet_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
            )
        outlet = db.query(Outlet).filter(Outlet.id == current_user.outlet_id).first()
        if outlet is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
            )
        return AuthMeResponse(
            id=current_user.id,
            name="Support Access",
            phone="",
            outlet_id=outlet.id,
            outlet_name=outlet.name,
            outlet_slug=outlet.slug,
            outlet_logo_url=outlet.logo_url,
            role_name="Support",
            permissions=sorted(current_user.permissions),
            is_support_session=True,
            require_customer_login=outlet.require_customer_login,
        )

    if current_user.user_type != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User access required",
        )

    user = current_user.db_user
    if not isinstance(user, User):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    all_memberships = (
        db.query(OutletMembership)
        .options(joinedload(OutletMembership.outlet), joinedload(OutletMembership.role))
        .filter(OutletMembership.user_id == user.id)
        .order_by(OutletMembership.created_at.asc())
        .all()
    )
    membership_summaries = _membership_summaries(all_memberships)

    outlet_id = current_user.outlet_id
    if outlet_id is None:
        return AuthMeResponse(
            id=user.id,
            name=user.name or "",
            phone=user.phone,
            email=user.email,
            avatar_url=user.avatar_url,
            date_of_birth=user.date_of_birth,
            gender=user.gender.value if user.gender else None,
            dietary_preferences=dietary_list(user),
            profile_completed_at=user.profile_completed_at,
            permissions=[],
            memberships=membership_summaries,
        )

    membership = (
        db.query(OutletMembership)
        .options(
            joinedload(OutletMembership.outlet),
            joinedload(OutletMembership.role)
            .joinedload(Role.role_permissions)
            .joinedload(RolePermission.permission),
        )
        .filter(
            OutletMembership.user_id == user.id,
            OutletMembership.outlet_id == outlet_id,
            OutletMembership.active_status.is_(True),
        )
        .first()
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active membership for this outlet",
        )

    permissions = sorted(rp.permission.key for rp in membership.role.role_permissions)
    return AuthMeResponse(
        id=user.id,
        name=user.name or "",
        phone=user.phone,
        email=user.email,
        avatar_url=user.avatar_url,
        date_of_birth=user.date_of_birth,
        gender=user.gender.value if user.gender else None,
        dietary_preferences=dietary_list(user),
        profile_completed_at=user.profile_completed_at,
        outlet_id=membership.outlet_id,
        outlet_name=membership.outlet.name,
        outlet_slug=membership.outlet.slug,
        outlet_logo_url=membership.outlet.logo_url,
        role_name=membership.role.name,
        permissions=permissions,
        memberships=membership_summaries,
        require_customer_login=membership.outlet.require_customer_login,
    )


@router.get("/me/profile", response_model=UserProfileResponse)
def get_my_profile(
    current_user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    user = current_user.db_user
    if not isinstance(user, User):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User access required",
        )
    return build_user_profile_response(db, user)


@router.patch("/me/profile", response_model=UserProfileResponse)
def patch_my_profile(
    payload: UserProfileUpdate,
    current_user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    user = current_user.db_user
    if not isinstance(user, User):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User access required",
        )
    user = update_user_profile(db, user, payload)
    return build_user_profile_response(db, user)


@router.post("/me/profile/avatar", response_model=UserProfileResponse)
async def upload_my_avatar(
    avatar: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    user = current_user.db_user
    if not isinstance(user, User):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User access required",
        )
    user.avatar_url = await store_user_avatar(user.id, avatar)
    if user.name and user.name.strip() and user.profile_completed_at is None:
        user.profile_completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return build_user_profile_response(db, user)


@router.delete("/me/profile/avatar", response_model=UserProfileResponse)
def delete_my_avatar(
    current_user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    user = current_user.db_user
    if not isinstance(user, User):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User access required",
        )
    user.avatar_url = None
    db.commit()
    db.refresh(user)
    return build_user_profile_response(db, user)


def _has_active_outlet_membership(db: Session, phone: str) -> bool:
    user = db.query(User).filter(User.phone == phone).first()
    if user is None:
        return False
    membership = (
        db.query(OutletMembership.id)
        .filter(
            OutletMembership.user_id == user.id,
            OutletMembership.active_status.is_(True),
        )
        .first()
    )
    return membership is not None


@router.post("/otp/request", response_model=OtpRequestResponse)
def request_otp(payload: OtpRequest, db: Session = Depends(get_db)):
    if payload.audience == "staff" and not _has_active_outlet_membership(db, payload.phone):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phone number not registered",
        )
    assert_otp_rate_limit(db, payload.phone, purpose="login")
    send_otp(db, payload.phone, purpose="login")
    return OtpRequestResponse(message=OTP_SUCCESS_MESSAGE)


def _token_response_from_pair(pair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
    )


@router.post("/otp/verify", response_model=TokenResponse)
def verify_otp_endpoint(payload: OtpVerifyRequest, db: Session = Depends(get_db)):
    verify_otp_for_purpose(db, payload.phone, payload.otp_code, purpose="login")

    user = find_or_create_user(db, payload.phone)
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    outlet_id_str, _ = _resolve_outlet_token(db, user)
    outlet_uuid = UUID(outlet_id_str) if outlet_id_str is not None else None

    pair = issue_tokens(
        db,
        session_kind="user",
        subject_id=user.id,
        outlet_id=outlet_uuid,
    )
    return _token_response_from_pair(pair)


@router.post("/select-outlet", response_model=TokenResponse)
def select_outlet(
    payload: SelectOutletRequest,
    current_user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    membership = (
        db.query(OutletMembership)
        .filter(
            OutletMembership.user_id == current_user.id,
            OutletMembership.outlet_id == payload.outlet_id,
            OutletMembership.active_status.is_(True),
        )
        .first()
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active membership for this outlet",
        )

    pair = issue_tokens(
        db,
        session_kind="user",
        subject_id=current_user.id,
        outlet_id=payload.outlet_id,
    )
    return _token_response_from_pair(pair)


@router.post("/refresh", response_model=TokenResponse)
def refresh_tokens(payload: RefreshRequest, db: Session = Depends(get_db)):
    pair = refresh_session(db, payload.refresh_token)
    return _token_response_from_pair(pair)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)):
    revoke_refresh_token(db, payload.refresh_token)
