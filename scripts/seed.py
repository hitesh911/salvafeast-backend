"""Seed permissions, default roles, and platform admin."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from decimal import Decimal

from app.core.config import settings
from app.core.plan_modules import DEFAULT_LIMITS_BY_SLUG, DEFAULT_MODULES_BY_SLUG, normalize_plan_features
from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models.enums import SubscriptionStatus
from app.models.outlet import Outlet
from app.models.outlet_subscription import OutletSubscription
from app.models.permission import Permission
from app.models.platform_admin import PlatformAdmin
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.subscription_plan import SubscriptionPlan
from app.services.platform.billing import assign_outlet_subscription, get_default_trial_plan

DEFAULT_PLANS = [
    {
        "name": "Starter",
        "slug": "starter",
        "price_monthly": Decimal("999"),
        "price_yearly": Decimal("9990"),
    },
    {
        "name": "Growth",
        "slug": "growth",
        "price_monthly": Decimal("2499"),
        "price_yearly": Decimal("24990"),
    },
    {
        "name": "Enterprise",
        "slug": "enterprise",
        "price_monthly": Decimal("4999"),
        "price_yearly": Decimal("49990"),
    },
]

MODULE_ACTIONS = {
    "menu": ("view", "edit"),
    "orders": ("view", "edit"),
    "staff": ("view", "edit"),
    "billing": ("view", "edit"),
    "analytics": ("view",),
    "offers": ("view", "edit"),
    "customers": ("view", "edit"),
    "tables": ("view", "edit"),
    "qr_studio": ("view", "edit"),
    "subscription": ("view", "edit"),
}

ROLE_PERMISSIONS = {
    "Owner": None,  # all permissions
    "Manager": [
        "menu.view",
        "menu.edit",
        "orders.view",
        "orders.edit",
        "customers.view",
        "customers.edit",
        "tables.view",
        "tables.edit",
        "qr_studio.view",
        "qr_studio.edit",
        "offers.view",
        "offers.edit",
        "analytics.view",
        "billing.view",
        "billing.edit",
        "subscription.view",
    ],
    "Staff": [
        "orders.view",
        "orders.edit",
        "menu.view",
        "tables.view",
        "customers.view",
    ],
}


def seed_permissions(db) -> dict[str, Permission]:
    permissions: dict[str, Permission] = {}
    for module, actions in MODULE_ACTIONS.items():
        for action in actions:
            key = f"{module}.{action}"
            perm = db.query(Permission).filter(Permission.key == key).first()
            if perm is None:
                perm = Permission(
                    key=key,
                    description=f"{action.capitalize()} {module}",
                    module=module,
                )
                db.add(perm)
                db.flush()
            permissions[key] = perm
    return permissions


def seed_roles(db, permissions: dict[str, Permission]) -> None:
    for role_name, perm_keys in ROLE_PERMISSIONS.items():
        role = (
            db.query(Role)
            .filter(
                Role.outlet_id.is_(None),
                Role.is_system_default.is_(True),
                Role.name == role_name,
            )
            .first()
        )
        if role is None:
            role = Role(
                outlet_id=None,
                name=role_name,
                is_system_default=True,
            )
            db.add(role)
            db.flush()

        if perm_keys is None:
            perm_keys = list(permissions.keys())

        existing_perm_ids = {
            rp.permission_id
            for rp in db.query(RolePermission).filter(RolePermission.role_id == role.id).all()
        }
        for key in perm_keys:
            perm = permissions[key]
            if perm.id not in existing_perm_ids:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))

    owner_keys = list(permissions.keys())
    manager_keys = ROLE_PERMISSIONS["Manager"]
    for role in db.query(Role).filter(Role.name == "Owner").all():
        existing_perm_ids = {
            rp.permission_id
            for rp in db.query(RolePermission).filter(RolePermission.role_id == role.id).all()
        }
        for key in owner_keys:
            perm = permissions[key]
            if perm.id not in existing_perm_ids:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    for role in db.query(Role).filter(Role.name == "Manager").all():
        existing_perm_ids = {
            rp.permission_id
            for rp in db.query(RolePermission).filter(RolePermission.role_id == role.id).all()
        }
        for key in manager_keys:
            perm = permissions.get(key)
            if perm is None:
                continue
            if perm.id not in existing_perm_ids:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))


def _plan_features_for_slug(slug: str) -> dict:
    return normalize_plan_features(
        None,
        modules=DEFAULT_MODULES_BY_SLUG[slug],
        limits=DEFAULT_LIMITS_BY_SLUG[slug],
    )


def seed_subscription_plans(db) -> None:
    for plan_data in DEFAULT_PLANS:
        slug = plan_data["slug"]
        features = _plan_features_for_slug(slug)
        existing = (
            db.query(SubscriptionPlan)
            .filter(SubscriptionPlan.slug == slug)
            .first()
        )
        if existing is None:
            db.add(
                SubscriptionPlan(
                    **plan_data,
                    features=features,
                    active_status=True,
                )
            )
        else:
            existing.name = plan_data["name"]
            existing.price_monthly = plan_data["price_monthly"]
            existing.price_yearly = plan_data["price_yearly"]
            existing.features = features
            existing.active_status = True


def seed_outlet_subscriptions(db) -> None:
    trial_plan = get_default_trial_plan(db)
    if trial_plan is None:
        return

    subscribed_outlet_ids = {
        row[0]
        for row in db.query(OutletSubscription.outlet_id).all()
    }
    for outlet in db.query(Outlet).all():
        if outlet.id in subscribed_outlet_ids:
            continue
        assign_outlet_subscription(
            db, outlet, trial_plan.id, SubscriptionStatus.trial, 14
        )


def seed_platform_admin(db) -> None:
    admin = db.query(PlatformAdmin).filter(
        PlatformAdmin.email == settings.PLATFORM_ADMIN_EMAIL
    ).first()
    if admin is None:
        admin = PlatformAdmin(
            name=settings.PLATFORM_ADMIN_NAME,
            email=settings.PLATFORM_ADMIN_EMAIL,
            password_hash=hash_password(settings.PLATFORM_ADMIN_PASSWORD),
        )
        db.add(admin)


def main() -> None:
    db = SessionLocal()
    try:
        permissions = seed_permissions(db)
        seed_roles(db, permissions)
        seed_subscription_plans(db)
        seed_outlet_subscriptions(db)
        seed_platform_admin(db)
        db.commit()
        print("Seed completed successfully.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
