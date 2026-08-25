from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from app.api.v1.deps import require_platform_admin
from app.core.security import (
    hash_password,
    verify_password,
)
from app.db.database import get_db
from app.models.enums import PlatformInvoiceStatus, SubscriptionStatus, VerificationStatus
from app.models.outlet import Outlet
from app.models.outlet_customer import OutletCustomer
from app.models.outlet_subscription import OutletSubscription
from app.models.outlet_membership import OutletMembership
from app.models.permission import Permission
from app.models.platform_admin import PlatformAdmin
from app.models.platform_audit_log import PlatformAuditLog
from app.models.platform_invoice import PlatformInvoice
from app.models.role import Role
from app.models.subscription_plan import SubscriptionPlan
from app.models.support_access_log import SupportAccessLog
from app.schemas.analytics import AnalyticsSummaryResponse
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.content_post import (
    ContentPostResponse,
    PaginatedPlatformContentPosts,
    PlatformContentPostSort,
)
from app.schemas.customer import (
    OutletCustomerDetail,
    OutletCustomerListItem,
    PaginatedOutletCustomers,
)
from app.schemas.order import OrderSummaryResponse
from app.schemas.outlet import (
    OutletCreate,
    OutletOnboardResponse,
    OutletResponse,
    OutletSettingsUpdate,
    OutletOwnerResponse,
)
from app.schemas.platform import (
    OutletSubscriptionAssign,
    OutletSubscriptionResponse,
    PaginatedPlatformAuditLogs,
    PaginatedPlatformCustomers,
    PaginatedSupportAccessLogs,
    PlatformAdminCreate,
    PlatformAdminListItem,
    PlatformAdminMeResponse,
    PlatformAdminUpdate,
    PlatformAnalyticsOverviewResponse,
    PlatformAuditLogItem,
    PlatformBillingOverviewResponse,
    PlatformCustomerDetailResponse,
    PlatformCustomerListItem,
    PlatformHealthAlert,
    PlatformInvoiceCreate,
    PlatformInvoiceResponse,
    PlatformInvoiceUpdate,
    PlatformOutletDetailResponse,
    PlatformOutletListItem,
    PlatformOutletProfileUpdate,
    PlatformOutletRevenueItem,
    PlatformOwnershipTransferRequest,
    PlatformOwnershipTransferResponse,
    PlatformPeakHoursResponse,
    PlatformPermissionItem,
    PlatformRevenueTrendResponse,
    PlatformRoleCreate,
    PlatformRoleItem,
    PlatformRoleUpdate,
    PlatformStaffCreate,
    PlatformStaffItem,
    PlatformStaffUpdate,
    PlatformTopItemsResponse,
    SubscriptionPlanCreate,
    SubscriptionPlanResponse,
    SubscriptionPlanUpdate,
    SupportAccessLogItem,
    SupportSessionResponse,
)
from app.services.analytics import (
    get_network_revenue_trend,
    get_peak_hours,
    get_platform_overview,
    get_revenue_trend,
    get_summary,
    get_top_items,
    resolve_date_range,
)
from app.services.content_posts import hide_post, list_posts_for_moderation, to_content_post_response
from app.services.platform.audit import log_platform_action
from app.services import ownership as ownership_service
from app.services import roles as roles_service
from app.services import staff as staff_service
from app.core.plan_modules import get_plan_limits, get_plan_modules
from app.services.platform.billing import (
    assign_outlet_subscription,
    billing_overview,
    create_platform_invoice,
    delete_plan,
    get_default_trial_plan,
    get_plan,
    invoice_to_dict,
    list_invoices,
    list_plans,
    list_subscriptions,
    subscription_to_dict,
)
from app.services import subscription as subscription_service
from app.services.platform.customers import (
    get_platform_customer_detail,
    list_platform_outlet_customers,
    search_platform_customers,
)
from app.services.platform.outlet_onboarding import seed_default_outlet_data
from app.services.outlet_address import apply_structured_address
from app.services.outlet_media import store_outlet_cover, store_outlet_logo
from app.services.platform.outlets import (
    compute_health_alerts,
    compute_mrr,
    count_overdue_invoices,
    count_trial_subscriptions,
    enrich_outlet_detail,
    enrich_outlet_list_item,
)
from app.services.refresh_tokens import issue_tokens

router = APIRouter(prefix="/platform", tags=["platform"])


def _get_outlet(db: Session, outlet_id: UUID) -> Outlet:
    outlet = db.query(Outlet).filter(Outlet.id == outlet_id).first()
    if outlet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outlet not found")
    return outlet


def _to_outlet_customer_list_item(outlet_customer: OutletCustomer) -> OutletCustomerListItem:
    user = outlet_customer.user
    return OutletCustomerListItem(
        user_id=user.id,
        phone=user.phone,
        name=user.name,
        total_orders=outlet_customer.total_orders,
        total_spend=outlet_customer.total_spend,
        first_visit_at=outlet_customer.first_visit_at,
        last_visit_at=outlet_customer.last_visit_at,
        marketing_opt_in=outlet_customer.marketing_opt_in,
    )


@router.post("/auth/login", response_model=TokenResponse)
def platform_admin_login(payload: LoginRequest, db: Session = Depends(get_db)):
    platform_admin = (
        db.query(PlatformAdmin).filter(PlatformAdmin.email == payload.email).first()
    )
    if (
        platform_admin
        and platform_admin.active_status
        and verify_password(payload.password, platform_admin.password_hash)
    ):
        pair = issue_tokens(
            db,
            session_kind="platform_admin",
            subject_id=platform_admin.id,
        )
        return TokenResponse(
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
            expires_in=pair.expires_in,
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
    )


@router.get("/auth/me", response_model=PlatformAdminMeResponse)
def platform_admin_me(
    admin=Depends(require_platform_admin),
):
    user = admin.db_user
    if not isinstance(user, PlatformAdmin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin")
    return PlatformAdminMeResponse(
        id=user.id, name=user.name, email=user.email, created_at=user.created_at
    )


@router.get("/analytics/overview", response_model=PlatformAnalyticsOverviewResponse)
def platform_analytics_overview(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    start, end, _, _ = resolve_date_range(from_date, to_date)
    (
        total_outlets,
        active_outlets,
        inactive_outlets,
        total_orders,
        total_revenue,
        top_outlets,
    ) = get_platform_overview(db, start, end)
    return PlatformAnalyticsOverviewResponse(
        total_outlets=total_outlets,
        active_outlets=active_outlets,
        inactive_outlets=inactive_outlets,
        total_orders=total_orders,
        total_revenue=total_revenue,
        mrr=compute_mrr(db),
        overdue_invoices_count=count_overdue_invoices(db),
        outlets_on_trial=count_trial_subscriptions(db),
        top_outlets_by_revenue=[
            PlatformOutletRevenueItem(
                outlet_id=outlet_id, outlet_name=outlet_name, revenue=revenue
            )
            for outlet_id, outlet_name, revenue in top_outlets
        ],
        health_alerts=[
            PlatformHealthAlert(**alert) for alert in compute_health_alerts(db)
        ],
    )


@router.get("/analytics/network-trend", response_model=PlatformRevenueTrendResponse)
def platform_network_trend(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    start, end, resolved_from, resolved_to = resolve_date_range(from_date, to_date)
    trend = get_network_revenue_trend(db, start, end, resolved_from, resolved_to)
    from app.schemas.analytics import RevenueTrendPoint

    return PlatformRevenueTrendResponse(
        points=[
            RevenueTrendPoint(
                date=day.isoformat(), revenue=revenue, order_count=order_count
            )
            for day, revenue, order_count in trend
        ]
    )


@router.get(
    "/outlets/{outlet_id}/analytics-summary",
    response_model=AnalyticsSummaryResponse,
)
def platform_outlet_analytics_summary(
    outlet_id: UUID,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    _get_outlet(db, outlet_id)
    start, end, _, _ = resolve_date_range(from_date, to_date)
    total_revenue, total_orders = get_summary(db, outlet_id, start, end)
    average_order_value = (
        (total_revenue / total_orders).quantize(Decimal("0.01"))
        if total_orders > 0
        else Decimal("0")
    )
    return AnalyticsSummaryResponse(
        total_revenue=total_revenue,
        total_orders=total_orders,
        average_order_value=average_order_value,
    )


@router.get(
    "/outlets/{outlet_id}/analytics/revenue-trend",
    response_model=PlatformRevenueTrendResponse,
)
def platform_outlet_revenue_trend(
    outlet_id: UUID,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    _get_outlet(db, outlet_id)
    start, end, resolved_from, resolved_to = resolve_date_range(from_date, to_date)
    trend = get_revenue_trend(db, outlet_id, start, end, resolved_from, resolved_to)
    from app.schemas.analytics import RevenueTrendPoint

    return PlatformRevenueTrendResponse(
        points=[
            RevenueTrendPoint(
                date=day.isoformat(), revenue=revenue, order_count=order_count
            )
            for day, revenue, order_count in trend
        ]
    )


@router.get(
    "/outlets/{outlet_id}/analytics/top-items",
    response_model=PlatformTopItemsResponse,
)
def platform_outlet_top_items(
    outlet_id: UUID,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    _get_outlet(db, outlet_id)
    start, end, _, _ = resolve_date_range(from_date, to_date)
    rows = get_top_items(db, outlet_id, start, end, limit)
    from app.schemas.analytics import ItemSalesPoint

    return PlatformTopItemsResponse(
        items=[
            ItemSalesPoint(
                menu_item_id=item_id,
                name=name,
                quantity_sold=quantity,
                revenue=revenue,
            )
            for item_id, name, quantity, revenue in rows
        ]
    )


@router.get(
    "/outlets/{outlet_id}/analytics/peak-hours",
    response_model=PlatformPeakHoursResponse,
)
def platform_outlet_peak_hours(
    outlet_id: UUID,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    _get_outlet(db, outlet_id)
    start, end, _, _ = resolve_date_range(from_date, to_date)
    rows = get_peak_hours(db, outlet_id, start, end)
    from app.schemas.analytics import PeakHourPoint

    return PlatformPeakHoursResponse(
        hours=[PeakHourPoint(hour=hour, order_count=count) for hour, count in rows]
    )


@router.post(
    "/outlets/{outlet_id}/support-session",
    response_model=SupportSessionResponse,
)
def create_support_session(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    outlet = _get_outlet(db, outlet_id)
    view_permissions = sorted(
        key for (key,) in db.query(Permission.key).filter(Permission.key.like("%.view")).all()
    )
    log = SupportAccessLog(platform_admin_id=admin.id, outlet_id=outlet.id)
    db.add(log)
    db.commit()

    session_meta = {
        "platform_admin_id": str(admin.id),
        "permissions": view_permissions,
    }
    pair = issue_tokens(
        db,
        session_kind="platform_support",
        subject_id=admin.id,
        outlet_id=outlet.id,
        session_meta=session_meta,
    )
    access_expires_at = datetime.now(timezone.utc) + timedelta(seconds=pair.expires_in)
    return SupportSessionResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
        outlet_id=outlet.id,
        outlet_name=outlet.name,
        outlet_slug=outlet.slug,
        expires_at=access_expires_at,
        refresh_expires_at=pair.refresh_expires_at,
    )


@router.get("/outlets", response_model=list[PlatformOutletListItem])
def list_outlets(
    verification_status: VerificationStatus | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    query = db.query(Outlet)
    if verification_status is not None:
        query = query.filter(Outlet.verification_status == verification_status)
    outlets = query.order_by(Outlet.created_at.desc()).all()
    return [
        PlatformOutletListItem(**enrich_outlet_list_item(db, outlet)) for outlet in outlets
    ]


@router.post("/outlets", response_model=OutletOnboardResponse, status_code=status.HTTP_201_CREATED)
def create_outlet(
    payload: OutletCreate,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    if db.query(Outlet).filter(Outlet.slug == payload.slug).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Outlet slug already exists")

    owner_role = (
        db.query(Role)
        .filter(Role.outlet_id.is_(None), Role.is_system_default.is_(True), Role.name == "Owner")
        .first()
    )
    if owner_role is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Default Owner role not found. Run the seed script first.",
        )

    from app.services.outlet_address import apply_structured_address
    from app.services.users import find_or_create_user

    outlet = Outlet(name=payload.name, slug=payload.slug)
    profile_fields = payload.model_dump(
        exclude={"name", "slug", "owner_name", "owner_phone"},
        exclude_none=True,
    )
    apply_structured_address(outlet, profile_fields)
    db.add(outlet)
    db.flush()
    seed_default_outlet_data(db, outlet)
    owner_user = find_or_create_user(db, payload.owner_phone, name=payload.owner_name)
    owner_membership = OutletMembership(
        user_id=owner_user.id,
        outlet_id=outlet.id,
        role_id=owner_role.id,
    )
    db.add(owner_membership)

    trial_plan = get_default_trial_plan(db)
    if trial_plan:
        assign_outlet_subscription(
            db, outlet, trial_plan.id, SubscriptionStatus.trial, 14
        )

    log_platform_action(
        db,
        actor_id=admin.id,
        action="outlet.created",
        resource_type="outlet",
        resource_id=outlet.id,
        metadata={"slug": outlet.slug, "owner_phone": payload.owner_phone},
    )
    db.commit()
    db.refresh(outlet)
    db.refresh(owner_membership)
    db.refresh(owner_user)
    return OutletOnboardResponse(
        outlet=OutletResponse.model_validate(outlet),
        owner=OutletOwnerResponse(
            membership_id=owner_membership.id,
            user_id=owner_user.id,
            outlet_id=owner_membership.outlet_id,
            name=owner_user.name or payload.owner_name,
            phone=owner_user.phone,
            email=owner_user.email,
            role_id=owner_membership.role_id,
            active_status=owner_membership.active_status,
            last_login=owner_user.last_login,
            created_at=owner_membership.created_at,
        ),
    )


@router.get("/outlets/{outlet_id}", response_model=PlatformOutletDetailResponse)
def get_outlet(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    outlet = _get_outlet(db, outlet_id)
    return PlatformOutletDetailResponse(**enrich_outlet_detail(db, outlet))


@router.patch("/outlets/{outlet_id}", response_model=PlatformOutletDetailResponse)
def update_outlet_profile(
    outlet_id: UUID,
    payload: PlatformOutletProfileUpdate,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    outlet = _get_outlet(db, outlet_id)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No fields to update")
    if "slug" in updates:
        existing = (
            db.query(Outlet)
            .filter(Outlet.slug == updates["slug"], Outlet.id != outlet.id)
            .first()
        )
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already in use")
    apply_structured_address(outlet, updates)
    log_platform_action(
        db,
        actor_id=admin.id,
        action="outlet.profile_updated",
        resource_type="outlet",
        resource_id=outlet.id,
        metadata=updates,
    )
    db.commit()
    db.refresh(outlet)
    return PlatformOutletDetailResponse(**enrich_outlet_detail(db, outlet))


@router.post("/outlets/{outlet_id}/logo", response_model=PlatformOutletDetailResponse)
async def upload_outlet_logo(
    outlet_id: UUID,
    logo: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    outlet = _get_outlet(db, outlet_id)
    outlet.logo_url = await store_outlet_logo(outlet_id, logo)
    log_platform_action(
        db,
        actor_id=admin.id,
        action="outlet.logo_uploaded",
        resource_type="outlet",
        resource_id=outlet.id,
        metadata={"filename": logo.filename},
    )
    db.commit()
    db.refresh(outlet)
    return PlatformOutletDetailResponse(**enrich_outlet_detail(db, outlet))


@router.delete("/outlets/{outlet_id}/logo", response_model=PlatformOutletDetailResponse)
def delete_outlet_logo(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    outlet = _get_outlet(db, outlet_id)
    outlet.logo_url = None
    log_platform_action(
        db,
        actor_id=admin.id,
        action="outlet.logo_removed",
        resource_type="outlet",
        resource_id=outlet.id,
        metadata={},
    )
    db.commit()
    db.refresh(outlet)
    return PlatformOutletDetailResponse(**enrich_outlet_detail(db, outlet))


@router.post("/outlets/{outlet_id}/cover", response_model=PlatformOutletDetailResponse)
async def upload_outlet_cover(
    outlet_id: UUID,
    cover: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    outlet = _get_outlet(db, outlet_id)
    outlet.cover_image_url = await store_outlet_cover(outlet_id, cover)
    log_platform_action(
        db,
        actor_id=admin.id,
        action="outlet.cover_uploaded",
        resource_type="outlet",
        resource_id=outlet.id,
        metadata={"filename": cover.filename},
    )
    db.commit()
    db.refresh(outlet)
    return PlatformOutletDetailResponse(**enrich_outlet_detail(db, outlet))


@router.delete("/outlets/{outlet_id}/cover", response_model=PlatformOutletDetailResponse)
def delete_outlet_cover(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    outlet = _get_outlet(db, outlet_id)
    outlet.cover_image_url = None
    log_platform_action(
        db,
        actor_id=admin.id,
        action="outlet.cover_removed",
        resource_type="outlet",
        resource_id=outlet.id,
        metadata={},
    )
    db.commit()
    db.refresh(outlet)
    return PlatformOutletDetailResponse(**enrich_outlet_detail(db, outlet))


@router.patch("/outlets/{outlet_id}/settings", response_model=PlatformOutletDetailResponse)
def update_outlet_settings(
    outlet_id: UUID,
    payload: OutletSettingsUpdate,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    outlet = _get_outlet(db, outlet_id)
    if (
        payload.require_customer_login is None
        and payload.require_prepaid is None
        and payload.active_status is None
        and payload.verification_status is None
    ):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one setting must be provided")
    changes = {}
    if payload.require_customer_login is not None:
        outlet.require_customer_login = payload.require_customer_login
        changes["require_customer_login"] = payload.require_customer_login
    if payload.require_prepaid is not None:
        outlet.require_prepaid = payload.require_prepaid
        changes["require_prepaid"] = payload.require_prepaid
    if payload.active_status is not None:
        outlet.active_status = payload.active_status
        changes["active_status"] = payload.active_status
    if payload.verification_status is not None:
        outlet.verification_status = payload.verification_status
        changes["verification_status"] = payload.verification_status.value
    log_platform_action(
        db,
        actor_id=admin.id,
        action="outlet.settings_updated",
        resource_type="outlet",
        resource_id=outlet.id,
        metadata=changes,
    )
    db.commit()
    db.refresh(outlet)
    return PlatformOutletDetailResponse(**enrich_outlet_detail(db, outlet))


def _staff_to_platform_item(membership: OutletMembership) -> PlatformStaffItem:
    user = membership.user
    return PlatformStaffItem(
        id=membership.id,
        user_id=user.id,
        outlet_id=membership.outlet_id,
        name=user.name or "",
        phone=user.phone,
        email=user.email,
        role_id=membership.role_id,
        role_name=membership.role.name if membership.role else "",
        active_status=membership.active_status,
        last_login=user.last_login,
        created_at=membership.created_at,
    )


def _role_to_platform_item(role: Role) -> PlatformRoleItem:
    return PlatformRoleItem(
        id=role.id,
        name=role.name,
        is_system_default=role.is_system_default,
        permission_keys=sorted(rp.permission.key for rp in role.role_permissions),
    )


@router.get("/permissions", response_model=list[PlatformPermissionItem])
def list_platform_permissions(
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    permissions = roles_service.list_permissions(db)
    return [
        PlatformPermissionItem(
            id=p.id,
            key=p.key,
            description=p.description,
            module=p.module,
        )
        for p in permissions
    ]


@router.get("/outlets/{outlet_id}/roles", response_model=list[PlatformRoleItem])
def list_outlet_roles(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    _get_outlet(db, outlet_id)
    roles = roles_service.list_roles(db, outlet_id)
    return [_role_to_platform_item(r) for r in roles]


@router.post("/outlets/{outlet_id}/roles", response_model=PlatformRoleItem, status_code=status.HTTP_201_CREATED)
def create_outlet_role(
    outlet_id: UUID,
    payload: PlatformRoleCreate,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    _get_outlet(db, outlet_id)
    role = roles_service.create_custom_role(
        db,
        outlet_id,
        name=payload.name,
        permission_ids=payload.permission_ids,
    )
    log_platform_action(
        db,
        actor_id=admin.id,
        action="outlet.role_created",
        resource_type="role",
        resource_id=role.id,
        metadata={"name": role.name, "outlet_id": str(outlet_id)},
    )
    return _role_to_platform_item(role)


@router.patch("/outlets/{outlet_id}/roles/{role_id}", response_model=PlatformRoleItem)
def update_outlet_role(
    outlet_id: UUID,
    role_id: UUID,
    payload: PlatformRoleUpdate,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    _get_outlet(db, outlet_id)
    role = roles_service.update_custom_role(
        db,
        outlet_id,
        role_id,
        name=payload.name,
        permission_ids=payload.permission_ids,
    )
    log_platform_action(
        db,
        actor_id=admin.id,
        action="outlet.role_updated",
        resource_type="role",
        resource_id=role.id,
        metadata={"name": role.name, "outlet_id": str(outlet_id)},
    )
    return _role_to_platform_item(role)


@router.delete("/outlets/{outlet_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_outlet_role(
    outlet_id: UUID,
    role_id: UUID,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    _get_outlet(db, outlet_id)
    roles_service.delete_custom_role(db, outlet_id, role_id)
    log_platform_action(
        db,
        actor_id=admin.id,
        action="outlet.role_deleted",
        resource_type="role",
        resource_id=role_id,
        metadata={"outlet_id": str(outlet_id)},
    )


@router.get("/outlets/{outlet_id}/staff", response_model=list[PlatformStaffItem])
def list_outlet_staff(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    _get_outlet(db, outlet_id)
    memberships = staff_service.list_staff(db, outlet_id)
    return [_staff_to_platform_item(membership) for membership in memberships]


@router.post("/outlets/{outlet_id}/staff", response_model=PlatformStaffItem, status_code=status.HTTP_201_CREATED)
def create_outlet_staff(
    outlet_id: UUID,
    payload: PlatformStaffCreate,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    _get_outlet(db, outlet_id)
    membership = staff_service.create_staff(
        db,
        outlet_id,
        name=payload.name,
        phone=payload.phone,
        role_id=payload.role_id,
        email=payload.email,
    )
    log_platform_action(
        db,
        actor_id=admin.id,
        action="outlet.staff_created",
        resource_type="outlet_membership",
        resource_id=membership.id,
        metadata={"phone": membership.user.phone, "role_id": str(membership.role_id)},
    )
    return _staff_to_platform_item(membership)


@router.patch("/outlets/{outlet_id}/staff/{membership_id}", response_model=PlatformStaffItem)
def update_outlet_staff(
    outlet_id: UUID,
    membership_id: UUID,
    payload: PlatformStaffUpdate,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    _get_outlet(db, outlet_id)
    membership = staff_service.update_staff(
        db,
        outlet_id,
        membership_id,
        name=payload.name,
        email=payload.email,
        active_status=payload.active_status,
        role_id=payload.role_id,
        is_platform=True,
    )
    changes = payload.model_dump(exclude_unset=True)
    if "role_id" in changes and changes["role_id"] is not None:
        changes["role_id"] = str(changes["role_id"])
    log_platform_action(
        db,
        actor_id=admin.id,
        action="outlet.staff_updated",
        resource_type="outlet_membership",
        resource_id=membership.id,
        metadata=changes,
    )
    return _staff_to_platform_item(membership)


@router.post("/outlets/{outlet_id}/transfer-ownership", response_model=PlatformOwnershipTransferResponse)
def transfer_outlet_ownership(
    outlet_id: UUID,
    payload: PlatformOwnershipTransferRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    _get_outlet(db, outlet_id)
    result = ownership_service.transfer_ownership(
        db,
        outlet_id,
        new_owner_membership_id=payload.new_owner_user_id,
        demote_previous_to=payload.demote_previous_to,
    )
    log_platform_action(
        db,
        actor_id=admin.id,
        action="outlet.ownership_transferred",
        resource_type="outlet",
        resource_id=outlet_id,
        metadata={
            "previous_owner_id": str(result["previous_owner_id"]),
            "new_owner_id": str(result["new_owner_id"]),
            "demote_previous_to": payload.demote_previous_to,
        },
    )
    return PlatformOwnershipTransferResponse(
        previous_owner_id=result["previous_owner_id"],
        new_owner_id=result["new_owner_id"],
    )


@router.get("/outlets/{outlet_id}/customers", response_model=PaginatedOutletCustomers)
def platform_list_outlet_customers(
    outlet_id: UUID,
    sort: str = Query(default="-last_visit_at"),
    min_orders: int | None = Query(default=None, ge=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    _get_outlet(db, outlet_id)
    rows, total = list_platform_outlet_customers(
        db, outlet_id, sort, min_orders, page, page_size
    )
    return PaginatedOutletCustomers(
        items=[_to_outlet_customer_list_item(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/customers", response_model=PaginatedPlatformCustomers)
def platform_search_customers(
    phone: str | None = Query(default=None),
    name: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    items, total = search_platform_customers(
        db, phone=phone, name=name, page=page, page_size=page_size
    )
    return PaginatedPlatformCustomers(
        items=[PlatformCustomerListItem(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/customers/{user_id}", response_model=PlatformCustomerDetailResponse)
def platform_get_customer(
    user_id: UUID,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    return PlatformCustomerDetailResponse(**get_platform_customer_detail(db, user_id))


@router.get("/support-access-logs", response_model=PaginatedSupportAccessLogs)
def list_support_access_logs(
    outlet_id: UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    query = (
        db.query(SupportAccessLog)
        .options(
            joinedload(SupportAccessLog.platform_admin),
            joinedload(SupportAccessLog.outlet),
        )
        .order_by(SupportAccessLog.started_at.desc())
    )
    if outlet_id is not None:
        query = query.filter(SupportAccessLog.outlet_id == outlet_id)
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedSupportAccessLogs(
        items=[
            SupportAccessLogItem(
                id=row.id,
                platform_admin_id=row.platform_admin_id,
                platform_admin_name=row.platform_admin.name if row.platform_admin else "",
                outlet_id=row.outlet_id,
                outlet_name=row.outlet.name if row.outlet else "",
                started_at=row.started_at,
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/audit-logs", response_model=PaginatedPlatformAuditLogs)
def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    query = (
        db.query(PlatformAuditLog)
        .options(joinedload(PlatformAuditLog.actor))
        .order_by(PlatformAuditLog.created_at.desc())
    )
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedPlatformAuditLogs(
        items=[
            PlatformAuditLogItem(
                id=row.id,
                actor_id=row.actor_id,
                actor_name=row.actor.name if row.actor else "",
                action=row.action,
                resource_type=row.resource_type,
                resource_id=row.resource_id,
                metadata_json=row.metadata_json,
                created_at=row.created_at,
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


def _plan_response(plan) -> SubscriptionPlanResponse:
    features = plan.features
    return SubscriptionPlanResponse(
        id=plan.id,
        name=plan.name,
        slug=plan.slug,
        price_monthly=plan.price_monthly,
        price_yearly=plan.price_yearly,
        features=features,
        included_modules=get_plan_modules(features, plan_slug=plan.slug),
        limits=get_plan_limits(features, plan_slug=plan.slug) or None,
        active_status=plan.active_status,
        created_at=plan.created_at,
    )


@router.get("/plans", response_model=list[SubscriptionPlanResponse])
def list_subscription_plans(
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    return [_plan_response(p) for p in list_plans(db)]


@router.post("/plans", response_model=SubscriptionPlanResponse, status_code=status.HTTP_201_CREATED)
def create_subscription_plan(
    payload: SubscriptionPlanCreate,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    if db.query(SubscriptionPlan).filter(SubscriptionPlan.slug == payload.slug).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Plan slug exists")

    features = subscription_service.normalize_plan_payload_features(
        payload.features,
        modules=payload.modules,
        limits=payload.limits,
    )
    plan = SubscriptionPlan(
        name=payload.name,
        slug=payload.slug,
        price_monthly=payload.price_monthly,
        price_yearly=payload.price_yearly,
        features=features,
        active_status=payload.active_status,
    )
    db.add(plan)
    log_platform_action(
        db, actor_id=admin.id, action="plan.created", resource_type="plan", resource_id=plan.id
    )
    db.commit()
    db.refresh(plan)
    return _plan_response(plan)


@router.patch("/plans/{plan_id}", response_model=SubscriptionPlanResponse)
def update_subscription_plan(
    plan_id: UUID,
    payload: SubscriptionPlanUpdate,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    plan = get_plan(db, plan_id)
    data = payload.model_dump(exclude_unset=True)
    modules = data.pop("modules", None)
    limits = data.pop("limits", None)
    if modules is not None or limits is not None or "features" in data:
        data["features"] = subscription_service.normalize_plan_payload_features(
            data.get("features", plan.features),
            modules=modules,
            limits=limits,
        )
    for key, value in data.items():
        setattr(plan, key, value)
    log_platform_action(
        db, actor_id=admin.id, action="plan.updated", resource_type="plan", resource_id=plan.id
    )
    db.commit()
    db.refresh(plan)
    return _plan_response(plan)


@router.get("/plans/{plan_id}", response_model=SubscriptionPlanResponse)
def get_subscription_plan(
    plan_id: UUID,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    return _plan_response(get_plan(db, plan_id))


@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subscription_plan(
    plan_id: UUID,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    delete_plan(db, plan_id)
    log_platform_action(
        db, actor_id=admin.id, action="plan.deleted", resource_type="plan", resource_id=plan_id
    )
    db.commit()


@router.get("/subscriptions", response_model=list[OutletSubscriptionResponse])
def list_all_subscriptions(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    sf = SubscriptionStatus(status_filter) if status_filter else None
    return [OutletSubscriptionResponse(**subscription_to_dict(s)) for s in list_subscriptions(db, sf)]


@router.put("/outlets/{outlet_id}/subscription", response_model=OutletSubscriptionResponse)
def assign_subscription(
    outlet_id: UUID,
    payload: OutletSubscriptionAssign,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    outlet = _get_outlet(db, outlet_id)
    sub = assign_outlet_subscription(
        db,
        outlet,
        payload.plan_id,
        payload.status,
        payload.trial_days,
        payload.billing_interval,
    )
    log_platform_action(
        db,
        actor_id=admin.id,
        action="subscription.assigned",
        resource_type="outlet_subscription",
        resource_id=sub.id,
        metadata={"plan_id": str(payload.plan_id), "status": payload.status.value},
    )
    db.commit()
    sub = (
        db.query(OutletSubscription)
        .options(
            joinedload(OutletSubscription.plan),
            joinedload(OutletSubscription.outlet),
        )
        .filter(OutletSubscription.id == sub.id)
        .first()
    )
    return OutletSubscriptionResponse(**subscription_to_dict(sub))


@router.get("/billing/overview", response_model=PlatformBillingOverviewResponse)
def get_billing_overview(
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    return PlatformBillingOverviewResponse(**billing_overview(db))


@router.get("/invoices", response_model=list[PlatformInvoiceResponse])
def list_platform_invoices(
    outlet_id: UUID | None = Query(default=None),
    status_filter: PlatformInvoiceStatus | None = Query(default=None, alias="status"),
    overdue_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    invoices = list_invoices(
        db, outlet_id=outlet_id, status_filter=status_filter, overdue_only=overdue_only
    )
    return [PlatformInvoiceResponse(**invoice_to_dict(inv)) for inv in invoices]


@router.post("/invoices", response_model=PlatformInvoiceResponse, status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: PlatformInvoiceCreate,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    outlet = _get_outlet(db, payload.outlet_id)
    invoice = create_platform_invoice(
        db,
        outlet,
        amount=payload.amount,
        period_start=payload.period_start,
        period_end=payload.period_end,
        due_date=payload.due_date,
        notes=payload.notes,
    )
    log_platform_action(
        db,
        actor_id=admin.id,
        action="invoice.created",
        resource_type="platform_invoice",
        resource_id=invoice.id,
    )
    db.commit()
    invoice = (
        db.query(PlatformInvoice)
        .options(joinedload(PlatformInvoice.outlet))
        .filter(PlatformInvoice.id == invoice.id)
        .first()
    )
    return PlatformInvoiceResponse(**invoice_to_dict(invoice))


@router.patch("/invoices/{invoice_id}", response_model=PlatformInvoiceResponse)
def update_invoice(
    invoice_id: UUID,
    payload: PlatformInvoiceUpdate,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    invoice = (
        db.query(PlatformInvoice)
        .options(joinedload(PlatformInvoice.outlet))
        .filter(PlatformInvoice.id == invoice_id)
        .first()
    )
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    if payload.status is not None:
        invoice.status = payload.status
        if payload.status == PlatformInvoiceStatus.paid:
            invoice.paid_at = datetime.now(timezone.utc)
    if payload.notes is not None:
        invoice.notes = payload.notes
    log_platform_action(
        db,
        actor_id=admin.id,
        action="invoice.updated",
        resource_type="platform_invoice",
        resource_id=invoice.id,
        metadata={"status": payload.status.value if payload.status else None},
    )
    db.commit()
    db.refresh(invoice)
    return PlatformInvoiceResponse(**invoice_to_dict(invoice))


@router.get("/admins", response_model=list[PlatformAdminListItem])
def list_platform_admins(
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    admins = db.query(PlatformAdmin).order_by(PlatformAdmin.created_at.asc()).all()
    return [
        PlatformAdminListItem(
            id=a.id, name=a.name, email=a.email, active_status=a.active_status, created_at=a.created_at
        )
        for a in admins
    ]


@router.post("/admins", response_model=PlatformAdminListItem, status_code=status.HTTP_201_CREATED)
def create_platform_admin(
    payload: PlatformAdminCreate,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    if db.query(PlatformAdmin).filter(PlatformAdmin.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
    new_admin = PlatformAdmin(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    db.add(new_admin)
    log_platform_action(
        db,
        actor_id=admin.id,
        action="admin.created",
        resource_type="platform_admin",
        resource_id=new_admin.id,
    )
    db.commit()
    db.refresh(new_admin)
    return PlatformAdminListItem(
        id=new_admin.id,
        name=new_admin.name,
        email=new_admin.email,
        active_status=new_admin.active_status,
        created_at=new_admin.created_at,
    )


@router.patch("/admins/{admin_id}", response_model=PlatformAdminListItem)
def update_platform_admin(
    admin_id: UUID,
    payload: PlatformAdminUpdate,
    db: Session = Depends(get_db),
    current=Depends(require_platform_admin),
):
    target = db.query(PlatformAdmin).filter(PlatformAdmin.id == admin_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found")
    if payload.name is not None:
        target.name = payload.name
    if payload.active_status is not None:
        target.active_status = payload.active_status
    if payload.password is not None:
        target.password_hash = hash_password(payload.password)
    log_platform_action(
        db,
        actor_id=current.id,
        action="admin.updated",
        resource_type="platform_admin",
        resource_id=target.id,
    )
    db.commit()
    db.refresh(target)
    return PlatformAdminListItem(
        id=target.id,
        name=target.name,
        email=target.email,
        active_status=target.active_status,
        created_at=target.created_at,
    )


@router.get("/content-posts", response_model=PaginatedPlatformContentPosts)
def list_content_posts_for_moderation(
    sort: PlatformContentPostSort = Query(default="most_reported"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current=Depends(require_platform_admin),
):
    return list_posts_for_moderation(db, sort=sort, page=page, page_size=page_size)


@router.patch("/content-posts/{post_id}/hide", response_model=ContentPostResponse)
def hide_content_post(
    post_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(require_platform_admin),
):
    post = hide_post(db, post_id)
    log_platform_action(
        db,
        actor_id=current.id,
        action="content_post.hidden",
        resource_type="content_post",
        resource_id=post.id,
    )
    db.commit()
    db.refresh(post)
    return to_content_post_response(post, db)
