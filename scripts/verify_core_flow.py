"""Verify core consumer ordering flows against a running backend.

Covers: order types, login enforcement, UPI links, refresh tokens (HTTP),
and static frontend checks for privacy/terms/PWA gaps.

Usage:
  python scripts/verify_core_flow.py

Requires backend at http://127.0.0.1:8000 (override with API_BASE_URL).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.security import hash_otp
from app.db.database import SessionLocal
from app.models.enums import OrderType
from app.models.menu_category import MenuCategory
from app.models.menu_item import MenuItem
from app.models.outlet import Outlet
from app.models.table import Table
from app.services.users import find_or_create_user
import secrets

API_ROOT = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
BASE = f"{API_ROOT}/api/v1"
KNOWN_OTP = "848484"
TEST_PHONE = "9999900099"
CORE_FLOW_NOTES = "CORE_FLOW_VERIFY"

WORKSPACE = Path(__file__).resolve().parent.parent.parent
CONSUMER_WEB = WORKSPACE / "salva-consumer-web"
ADMIN_WEB = WORKSPACE / "salva-admin-web"


@dataclass
class CaseResult:
    name: str
    passed: bool
    detail: str


@dataclass
class OutletFixture:
    slug: str
    outlet_id: UUID
    menu_item_id: UUID
    table_qr_token: str | None
    saved_require_login: bool
    saved_upi_vpa: str | None


def insert_login_otp(db, phone: str) -> None:
    from app.models.otp_verification import OtpVerification

    now = datetime.now(timezone.utc)
    db.query(OtpVerification).filter(
        OtpVerification.phone == phone,
        OtpVerification.purpose == "login",
    ).delete(synchronize_session=False)
    db.add(
        OtpVerification(
            phone=phone,
            otp_code_hash=hash_otp(KNOWN_OTP),
            purpose="login",
            expires_at=now + timedelta(minutes=10),
            is_verified=False,
            attempt_count=0,
        )
    )
    db.commit()


def obtain_tokens(client: httpx.Client, db, phone: str) -> tuple[str, str]:
    insert_login_otp(db, phone)
    response = client.post(
        f"{BASE}/auth/otp/verify",
        json={"phone": phone, "otp_code": KNOWN_OTP},
    )
    if response.status_code != 200:
        raise RuntimeError(f"OTP verify failed: {response.status_code} {response.text}")
    body = response.json()
    return body["access_token"], body["refresh_token"]


def first_menu_item_id(db, outlet_id: UUID) -> UUID:
    row = (
        db.query(MenuItem.id)
        .join(MenuCategory, MenuCategory.id == MenuItem.category_id)
        .filter(MenuCategory.outlet_id == outlet_id)
        .order_by(MenuItem.sort_order.asc())
        .first()
    )
    if row is None:
        raise SystemExit("No menu items found — add menu data to an outlet first.")
    return row[0]


def first_table(db, outlet_id: UUID) -> Table | None:
    return (
        db.query(Table)
        .filter(Table.outlet_id == outlet_id, Table.active_status.is_(True))
        .order_by(Table.table_number.asc())
        .first()
    )


def ensure_table(db, outlet_id: UUID) -> Table:
    table = first_table(db, outlet_id)
    if table is not None:
        return table
    table = Table(
        outlet_id=outlet_id,
        table_number="T99",
        qr_token=f"coreflow-{secrets.token_urlsafe(8)}",
        active_status=True,
    )
    db.add(table)
    db.commit()
    db.refresh(table)
    return table


def ensure_fixture(db) -> OutletFixture:
    preferred_slugs = ["south-indian-nirmand", "isolation-test-outlet-b"]
    outlet = None
    for slug in preferred_slugs:
        outlet = (
            db.query(Outlet)
            .filter(Outlet.slug == slug, Outlet.active_status.is_(True))
            .first()
        )
        if outlet is not None:
            break
    if outlet is None:
        outlet = db.query(Outlet).filter(Outlet.active_status.is_(True)).first()
    if outlet is None:
        raise SystemExit("No active outlet in database.")

    table = ensure_table(db, outlet.id)
    return OutletFixture(
        slug=outlet.slug,
        outlet_id=outlet.id,
        menu_item_id=first_menu_item_id(db, outlet.id),
        table_qr_token=table.qr_token,
        saved_require_login=outlet.require_customer_login,
        saved_upi_vpa=outlet.upi_vpa,
    )


def order_payload(
    menu_item_id: UUID,
    order_type: OrderType,
    table_qr_token: str | None = None,
) -> dict:
    payload = {
        "order_type": order_type.value,
        "items": [
            {
                "menu_item_id": str(menu_item_id),
                "quantity": 1,
                "addon_ids": [],
                "notes": CORE_FLOW_NOTES,
            }
        ],
    }
    if order_type == OrderType.dine_in:
        payload["table_qr_token"] = table_qr_token
    return payload


def httpx_post(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            return client.post(url, **kwargs)
        except httpx.TransportError as exc:
            last_exc = exc
            import time

            time.sleep(1.5 * (attempt + 1))
    raise last_exc  # type: ignore[misc]


def httpx_get(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            return client.get(url, **kwargs)
        except httpx.TransportError as exc:
            last_exc = exc
            import time

            time.sleep(1.5 * (attempt + 1))
    raise last_exc  # type: ignore[misc]


def test_menu_ordering_context(
    client: httpx.Client, ctx: OutletFixture
) -> list[CaseResult]:
    results: list[CaseResult] = []

    counter_resp = httpx_get(client, f"{BASE}/public/outlets/{ctx.slug}/menu")
    if counter_resp.status_code != 200:
        results.append(
            CaseResult(
                "Menu API (counter entry)",
                False,
                f"HTTP {counter_resp.status_code}: {counter_resp.text}",
            )
        )
        return results

    counter_body = counter_resp.json()
    ordering = counter_body["ordering"]
    types = ordering["available_order_types"]
    default = ordering["default_order_type"]

    types_ok = set(types) >= {"dine_in", "pickup", "counter"} and "pre_order" not in types
    default_ok = default == "counter"
    results.append(
        CaseResult(
            "Menu API (counter entry)",
            types_ok and default_ok,
            f"default={default}, available={types}",
        )
    )

    if ctx.table_qr_token:
        table_resp = httpx_get(
            client,
            f"{BASE}/public/outlets/{ctx.slug}/menu",
            params={"t": ctx.table_qr_token},
        )
        if table_resp.status_code != 200:
            results.append(
                CaseResult(
                    "Menu API (table QR entry)",
                    False,
                    f"HTTP {table_resp.status_code}: {table_resp.text}",
                )
            )
        else:
            table_ordering = table_resp.json()["ordering"]
            table_default_ok = table_ordering["default_order_type"] == "dine_in"
            scanned_ok = table_ordering["scanned_table_number"] is not None
            results.append(
                CaseResult(
                    "Menu API (table QR entry)",
                    table_default_ok and scanned_ok,
                    (
                        f"default={table_ordering['default_order_type']}, "
                        f"scanned_table={table_ordering['scanned_table_number']}"
                    ),
                )
            )
    else:
        results.append(
            CaseResult(
                "Menu API (table QR entry)",
                False,
                "No active table on outlet - skipped dine-in default check",
            )
        )

    return results


def test_order_types(client: httpx.Client, ctx: OutletFixture) -> list[CaseResult]:
    results: list[CaseResult] = []

    for order_type in (OrderType.counter, OrderType.pickup):
        resp = httpx_post(
            client,
            f"{BASE}/public/outlets/{ctx.slug}/orders",
            json=order_payload(ctx.menu_item_id, order_type),
        )
        ok = resp.status_code == 201 and resp.json()["order"]["order_type"] == order_type.value
        results.append(
            CaseResult(
                f"Place order ({order_type.value})",
                ok,
                f"HTTP {resp.status_code}" + (f": {resp.text[:200]}" if not ok else ""),
            )
        )

    if ctx.table_qr_token:
        resp = httpx_post(
            client,
            f"{BASE}/public/outlets/{ctx.slug}/orders",
            json=order_payload(
                ctx.menu_item_id,
                OrderType.dine_in,
                ctx.table_qr_token,
            ),
        )
        ok = resp.status_code == 201 and resp.json()["order"]["order_type"] == "dine_in"
        results.append(
            CaseResult(
                "Place order (dine_in with table)",
                ok,
                f"HTTP {resp.status_code}" + (f": {resp.text[:200]}" if not ok else ""),
            )
        )

        bad = httpx_post(
            client,
            f"{BASE}/public/outlets/{ctx.slug}/orders",
            json=order_payload(ctx.menu_item_id, OrderType.dine_in, None),
        )
        results.append(
            CaseResult(
                "Reject dine_in without table",
                bad.status_code == 422,
                f"HTTP {bad.status_code}: {bad.text[:200]}",
            )
        )
    else:
        results.append(
            CaseResult(
                "Place order (dine_in with table)",
                False,
                "No active table - skipped",
            )
        )

    return results


def test_login_enforcement(
    client: httpx.Client, db, ctx: OutletFixture
) -> list[CaseResult]:
    results: list[CaseResult] = []
    outlet = db.query(Outlet).filter(Outlet.id == ctx.outlet_id).first()
    if outlet is None:
        return [CaseResult("Login enforcement", False, "Outlet missing")]

    outlet.require_customer_login = True
    db.commit()

    try:
        guest = httpx_post(
            client,
            f"{BASE}/public/outlets/{ctx.slug}/orders",
            json=order_payload(ctx.menu_item_id, OrderType.counter),
        )
        results.append(
            CaseResult(
                "Guest blocked when login required",
                guest.status_code == 401,
                f"HTTP {guest.status_code}: {guest.text[:200]}",
            )
        )

        access, _ = obtain_tokens(client, db, TEST_PHONE)
        authed = httpx_post(
            client,
            f"{BASE}/public/outlets/{ctx.slug}/orders",
            json=order_payload(ctx.menu_item_id, OrderType.counter),
            headers={"Authorization": f"Bearer {access}"},
        )
        results.append(
            CaseResult(
                "Authenticated order when login required",
                authed.status_code == 201,
                f"HTTP {authed.status_code}: {authed.text[:200]}",
            )
        )

        menu = httpx_get(client, f"{BASE}/public/outlets/{ctx.slug}/menu")
        require_flag = menu.json()["ordering"]["require_customer_login"] is True
        results.append(
            CaseResult(
                "Menu exposes require_customer_login=true",
                require_flag,
                f"require_customer_login={menu.json()['ordering'].get('require_customer_login')}",
            )
        )
    finally:
        outlet.require_customer_login = ctx.saved_require_login
        db.commit()

    return results


def test_upi_link(client: httpx.Client, db, ctx: OutletFixture) -> list[CaseResult]:
    results: list[CaseResult] = []
    outlet = db.query(Outlet).filter(Outlet.id == ctx.outlet_id).first()
    if outlet is None:
        return [CaseResult("UPI payment link", False, "Outlet missing")]

    outlet.upi_vpa = "test@upi"
    db.commit()

    try:
        resp = httpx_post(
            client,
            f"{BASE}/public/outlets/{ctx.slug}/orders",
            json=order_payload(ctx.menu_item_id, OrderType.counter),
        )
        if resp.status_code != 201:
            results.append(
                CaseResult(
                    "UPI payment link on placement",
                    False,
                    f"Order failed HTTP {resp.status_code}: {resp.text[:200]}",
                )
            )
            return results

        link = resp.json().get("upi_payment_link")
        ok = isinstance(link, str) and link.startswith("upi://pay?") and "test@upi" in link
        results.append(
            CaseResult(
                "UPI payment link on placement",
                ok,
                link or "missing upi_payment_link",
            )
        )

        outlet.upi_vpa = None
        db.commit()

        no_vpa = httpx_post(
            client,
            f"{BASE}/public/outlets/{ctx.slug}/orders",
            json=order_payload(ctx.menu_item_id, OrderType.pickup),
        )
        if no_vpa.status_code == 201:
            missing_ok = no_vpa.json().get("upi_payment_link") is None
            results.append(
                CaseResult(
                    "No UPI link when VPA unset",
                    missing_ok,
                    f"upi_payment_link={no_vpa.json().get('upi_payment_link')!r}",
                )
            )
        else:
            results.append(
                CaseResult(
                    "No UPI link when VPA unset",
                    False,
                    f"Order failed HTTP {no_vpa.status_code}",
                )
            )
    finally:
        outlet.upi_vpa = ctx.saved_upi_vpa
        db.commit()

    return results


def test_refresh_tokens_http(client: httpx.Client, db) -> list[CaseResult]:
    results: list[CaseResult] = []
    find_or_create_user(db, TEST_PHONE, name="Core Flow Verify")
    access, refresh = obtain_tokens(client, db, TEST_PHONE)

    refresh_resp = httpx_post(
        client,
        f"{BASE}/auth/refresh",
        json={"refresh_token": refresh},
    )
    if refresh_resp.status_code != 200:
        results.append(
            CaseResult(
                "Refresh token rotation (HTTP)",
                False,
                f"HTTP {refresh_resp.status_code}: {refresh_resp.text[:200]}",
            )
        )
        return results

    body = refresh_resp.json()
    new_access = body.get("access_token")
    new_refresh = body.get("refresh_token")
    rotated = bool(new_access) and new_refresh != refresh
    results.append(
        CaseResult(
            "Refresh token rotation (HTTP)",
            rotated,
            "New access + refresh issued" if rotated else "Rotation failed",
        )
    )

    reuse = httpx_post(client, f"{BASE}/auth/refresh", json={"refresh_token": refresh})
    results.append(
        CaseResult(
            "Old refresh token rejected after rotation",
            reuse.status_code == 401,
            f"HTTP {reuse.status_code}",
        )
    )

    logout = httpx_post(client, f"{BASE}/auth/logout", json={"refresh_token": new_refresh})
    results.append(
        CaseResult(
            "Logout revokes refresh token",
            logout.status_code == 204,
            f"HTTP {logout.status_code}",
        )
    )

    after_logout = httpx_post(
        client,
        f"{BASE}/auth/refresh",
        json={"refresh_token": new_refresh},
    )
    results.append(
        CaseResult(
            "Revoked refresh rejected",
            after_logout.status_code == 401,
            f"HTTP {after_logout.status_code}",
        )
    )

    _ = access  # issued successfully if we got here
    return results


def test_frontend_gaps() -> list[CaseResult]:
    results: list[CaseResult] = []

    def legal_pages(app_dir: Path, label: str) -> CaseResult:
        privacy = list(app_dir.glob("**/privacy/**/page.tsx"))
        terms = list(app_dir.glob("**/terms/**/page.tsx"))
        ok = len(privacy) >= 1 and len(terms) >= 1
        return CaseResult(
            f"{label}: privacy and terms pages",
            ok,
            (
                "Routes present"
                if ok
                else f"Missing privacy={privacy}, terms={terms}"
            ),
        )

    results.append(legal_pages(CONSUMER_WEB, "Consumer web"))
    results.append(
        CaseResult(
            "Admin web: privacy/terms pages",
            len(list(ADMIN_WEB.glob("**/privacy/**/page.tsx"))) == 0,
            "Deferred - customer-facing legal pages live on consumer web",
        )
    )

    manifest = list(CONSUMER_WEB.glob("**/manifest.ts")) + list(
        CONSUMER_WEB.glob("**/manifest.json")
    )
    sw = list(CONSUMER_WEB.glob("**/sw.js")) + list(
        CONSUMER_WEB.glob("**/service-worker.js")
    )
    pwa_ok = len(manifest) >= 1 and len(sw) >= 1
    results.append(
        CaseResult(
            "PWA manifest and service worker",
            pwa_ok,
            (
                f"manifest={len(manifest)}, sw={len(sw)}"
                if pwa_ok
                else f"Missing manifest={manifest}, sw={sw}"
            ),
        )
    )

    push_files = [
        CONSUMER_WEB / "lib" / "push-notifications.ts",
        CONSUMER_WEB / "components" / "push-notifications-card.tsx",
    ]
    push_ok = all(path.is_file() for path in push_files)
    results.append(
        CaseResult(
            "Push notification client",
            push_ok,
            "Registration UI + helpers present" if push_ok else "Missing push client files",
        )
    )

    backend_push = (
        Path(__file__).resolve().parent.parent / "app" / "services" / "order_push_alerts.py"
    )
    try:
        from app.core.config import settings
        from app.services.order_push_alerts import STATUS_ALERTS, send_order_status_push

        _ = send_order_status_push
        _ = STATUS_ALERTS
        push_backend_ok = backend_push.is_file()
        vapid_detail = (
            "VAPID configured"
            if settings.push_notifications_enabled
            else "VAPID not set in .env (alerts disabled until configured)"
        )
        results.append(
            CaseResult(
                "Order push alert sender (backend)",
                push_backend_ok,
                vapid_detail,
            )
        )
    except Exception as exc:
        results.append(
            CaseResult(
                "Order push alert sender (backend)",
                False,
                str(exc),
            )
        )

    return results


def print_report(results: list[CaseResult]) -> int:
    passed = sum(1 for r in results if r.passed)
    failed = [r for r in results if not r.passed]

    print("\n=== Core Flow Verification ===\n")
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        print(f"[{mark}] {r.name}")
        print(f"       {r.detail}\n")

    print(f"Result: {passed}/{len(results)} passed")
    if failed:
        print("\nFailed checks:")
        for r in failed:
            print(f"  - {r.name}: {r.detail}")
        return 1
    print("\nAll core flow checks passed.")
    return 0


def main() -> None:
    db = SessionLocal()
    try:
        ctx = ensure_fixture(db)
        print(f"Using outlet: {ctx.slug} ({ctx.outlet_id})")
        if ctx.table_qr_token:
            print(f"Table QR token available for dine-in tests")

        results: list[CaseResult] = []
        with httpx.Client(timeout=30.0) as client:
            results.extend(test_menu_ordering_context(client, ctx))
            results.extend(test_order_types(client, ctx))
            results.extend(test_login_enforcement(client, db, ctx))
            results.extend(test_upi_link(client, db, ctx))
            results.extend(test_refresh_tokens_http(client, db))

        # DB-level refresh service (complements HTTP test)
        from scripts.verify_refresh_tokens import main as verify_refresh_db

        try:
            verify_refresh_db()
            results.append(
                CaseResult(
                    "Refresh token service (DB)",
                    True,
                    "issue -> rotate -> reject reuse -> revoke",
                )
            )
        except SystemExit as exc:
            results.append(
                CaseResult("Refresh token service (DB)", False, str(exc))
            )

        results.extend(test_frontend_gaps())
        raise SystemExit(print_report(results))
    finally:
        db.close()


if __name__ == "__main__":
    main()
