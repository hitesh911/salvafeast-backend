"""Canonical outlet modules included in subscription plans."""

PLAN_MODULE_LABELS: dict[str, str] = {
    "menu": "Menu",
    "orders": "Orders",
    "tables": "Tables",
    "qr_studio": "QR Studio",
    "offers": "Offers",
    "analytics": "Analytics",
    "billing": "Billing",
    "customers": "Customers",
    "staff": "Staff & Roles",
    "subscription": "Subscription",
}

ALL_PLAN_MODULES: tuple[str, ...] = tuple(PLAN_MODULE_LABELS.keys())

DEFAULT_MODULES_BY_SLUG: dict[str, list[str]] = {
    "starter": ["menu", "orders", "tables", "billing", "staff", "subscription"],
    "growth": [
        "menu",
        "orders",
        "tables",
        "billing",
        "staff",
        "subscription",
        "qr_studio",
        "offers",
        "customers",
        "analytics",
    ],
    "enterprise": list(ALL_PLAN_MODULES),
}

DEFAULT_LIMITS_BY_SLUG: dict[str, dict[str, int | str]] = {
    "starter": {"staff": 3},
    "growth": {"staff": 10},
    "enterprise": {"staff": "unlimited"},
}


def validate_module_keys(modules: list[str]) -> list[str]:
    invalid = [m for m in modules if m not in PLAN_MODULE_LABELS]
    if invalid:
        raise ValueError(f"Invalid plan modules: {', '.join(invalid)}")
    return sorted(set(modules), key=lambda m: ALL_PLAN_MODULES.index(m))


def normalize_plan_features(
    features: dict | None,
    *,
    modules: list[str] | None = None,
    limits: dict | None = None,
) -> dict:
    normalized: dict = dict(features or {})
    if modules is not None:
        normalized["modules"] = validate_module_keys(modules)
    elif "modules" in normalized:
        normalized["modules"] = validate_module_keys(list(normalized["modules"]))
    if limits is not None:
        normalized["limits"] = limits
    return normalized


def get_plan_modules(features: dict | None, *, plan_slug: str | None = None) -> list[str]:
    if features and isinstance(features.get("modules"), list):
        return list(features["modules"])
    if plan_slug and plan_slug in DEFAULT_MODULES_BY_SLUG:
        return list(DEFAULT_MODULES_BY_SLUG[plan_slug])
    return list(ALL_PLAN_MODULES)


def get_plan_limits(features: dict | None, *, plan_slug: str | None = None) -> dict:
    if features and isinstance(features.get("limits"), dict):
        return dict(features["limits"])
    if plan_slug and plan_slug in DEFAULT_LIMITS_BY_SLUG:
        return dict(DEFAULT_LIMITS_BY_SLUG[plan_slug])
    return {}


def get_staff_limit(features: dict | None, *, plan_slug: str | None = None) -> int | None:
    limits = get_plan_limits(features, plan_slug=plan_slug)
    staff = limits.get("staff")
    if staff is None or staff == "unlimited":
        return None
    try:
        return int(staff)
    except (TypeError, ValueError):
        return None
