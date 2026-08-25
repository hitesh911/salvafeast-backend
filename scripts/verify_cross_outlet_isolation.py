"""Cross-outlet isolation audit via HTTP (httpx) against a running backend.

Setup/fixtures use the DB for idempotent test data and known OTP injection.
All isolation assertions go through the real HTTP layer (routes + dependencies).

Usage:
  python scripts/verify_cross_outlet_isolation.py

Requires backend at http://127.0.0.1:8000 (override with API_BASE_URL).
"""

from __future__ import annotations

import base64
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.security import hash_otp
from app.db.database import SessionLocal
from app.models.enums import OrderType, SubscriptionStatus
from app.models.menu_category import MenuCategory
from app.models.menu_item import MenuItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.outlet import Outlet
from app.models.outlet_customer import OutletCustomer
from app.models.outlet_membership import OutletMembership
from app.models.otp_verification import OtpVerification
from app.models.role import Role
from app.models.user import User
from app.services.platform.billing import assign_outlet_subscription, get_default_trial_plan
from app.services.users import find_or_create_user

DEFAULT_MENU_CATEGORIES = [
    "Starters",
    "Main Course",
    "Rice & Breads",
    "Beverages",
    "Desserts",
]

API_ROOT = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
BASE = f"{API_ROOT}/api/v1"

OUTLET_A_SLUG = "south-indian-nirmand"
OUTLET_B_SLUG = "isolation-test-outlet-b"
TEST_PHONE = "9999900001"
KNOWN_OTP = "848484"
ORDER_ITEM_NOTES = "ISOLATION_TEST_ORDER"


@dataclass
class FixtureContext:
    outlet_a_id: UUID
    outlet_a_slug: str
    outlet_b_id: UUID
    outlet_b_slug: str
    user_id: UUID
    menu_item_b_id: UUID
    baseline_a_orders: int | None
    baseline_a_spend: str | None


@dataclass
class TestCaseResult:
    name: str
    passed: bool
    detail: str


def decode_jwt_payload(token: str) -> dict:
    part = token.split(".")[1]
    padding = "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(part + padding))


def insert_login_otp(db, phone: str) -> None:
    now = datetime.now(timezone.utc)
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


def httpx_verify_otp(client: httpx.Client, phone: str) -> dict:
    response = client.post(
        f"{BASE}/auth/otp/verify",
        json={"phone": phone, "otp_code": KNOWN_OTP},
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"OTP verify failed ({response.status_code}): {response.text}"
        )
    return response.json()


def obtain_consumer_token(client: httpx.Client, db, phone: str) -> str:
    """Token with no outlet_id: verify while staff membership is temporarily inactive."""
    user = db.query(User).filter(User.phone == phone).first()
    if user is None:
        raise RuntimeError("Test user missing during consumer token setup")

    membership = (
        db.query(OutletMembership)
        .filter(OutletMembership.user_id == user.id)
        .first()
    )
    if membership is None:
        raise RuntimeError("Test user membership missing during consumer token setup")

    membership.active_status = False
    db.commit()

    try:
        insert_login_otp(db, phone)
        data = httpx_verify_otp(client, phone)
        payload = decode_jwt_payload(data["access_token"])
        if payload.get("outlet_id"):
            raise RuntimeError(
                f"Expected consumer token without outlet_id, got outlet_id={payload.get('outlet_id')}"
            )
        return data["access_token"]
    finally:
        membership.active_status = True
        db.commit()


def obtain_staff_token(client: httpx.Client, db, phone: str, outlet_a_id: UUID) -> str:
    insert_login_otp(db, phone)
    data = httpx_verify_otp(client, phone)
    payload = decode_jwt_payload(data["access_token"])
    token_outlet = payload.get("outlet_id")
    if token_outlet and UUID(str(token_outlet)) == outlet_a_id:
        return data["access_token"]

    # Multi-outlet or missing outlet in verify response — select explicitly.
    response = client.post(
        f"{BASE}/auth/select-outlet",
        json={"outlet_id": str(outlet_a_id)},
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"select-outlet failed ({response.status_code}): {response.text}"
        )
    return response.json()["access_token"]


def seed_outlet_b_menu(db, outlet_b: Outlet) -> MenuCategory:
    existing = (
        db.query(MenuCategory.id)
        .filter(MenuCategory.outlet_id == outlet_b.id)
        .first()
    )
    if existing is None:
        for sort_order, name in enumerate(DEFAULT_MENU_CATEGORIES):
            db.add(
                MenuCategory(
                    outlet_id=outlet_b.id,
                    name=name,
                    sort_order=sort_order,
                )
            )
        db.flush()

    category = (
        db.query(MenuCategory)
        .filter(MenuCategory.outlet_id == outlet_b.id)
        .order_by(MenuCategory.sort_order.asc())
        .first()
    )
    if category is None:
        raise SystemExit("Failed to seed Outlet B menu categories.")
    return category


def ensure_fixtures(db) -> FixtureContext:
    outlet_a = db.query(Outlet).filter(Outlet.slug == OUTLET_A_SLUG).first()
    if outlet_a is None:
        raise SystemExit(
            f"Outlet A '{OUTLET_A_SLUG}' not found — seed or create it first."
        )

    outlet_b = db.query(Outlet).filter(Outlet.slug == OUTLET_B_SLUG).first()
    if outlet_b is None:
        outlet_b = Outlet(
            name="Isolation Test Outlet B",
            slug=OUTLET_B_SLUG,
            active_status=True,
            require_customer_login=False,
        )
        db.add(outlet_b)
        db.flush()

    category = seed_outlet_b_menu(db, outlet_b)

    trial_plan = get_default_trial_plan(db)
    if trial_plan is not None:
        from app.models.outlet_subscription import OutletSubscription

        has_sub = (
            db.query(OutletSubscription)
            .filter(OutletSubscription.outlet_id == outlet_b.id)
            .first()
        )
        if has_sub is None:
            assign_outlet_subscription(
                db, outlet_b, trial_plan.id, SubscriptionStatus.trial, 14
            )

    owner_role = (
        db.query(Role)
        .filter(
            Role.outlet_id.is_(None),
            Role.is_system_default.is_(True),
            Role.name == "Owner",
        )
        .first()
    )
    if owner_role is None:
        raise SystemExit("Owner system role missing — run seed.py first.")

    user = find_or_create_user(db, TEST_PHONE, name="Isolation Test User")

    # Remove any staff membership at outlet B (staff ONLY at A).
    db.query(OutletMembership).filter(
        OutletMembership.user_id == user.id,
        OutletMembership.outlet_id == outlet_b.id,
    ).delete(synchronize_session=False)

    membership_a = (
        db.query(OutletMembership)
        .filter(
            OutletMembership.user_id == user.id,
            OutletMembership.outlet_id == outlet_a.id,
        )
        .first()
    )
    if membership_a is None:
        membership_a = OutletMembership(
            user_id=user.id,
            outlet_id=outlet_a.id,
            role_id=owner_role.id,
            active_status=True,
        )
        db.add(membership_a)
    else:
        membership_a.role_id = owner_role.id
        membership_a.active_status = True

    menu_item = (
        db.query(MenuItem)
        .filter(
            MenuItem.outlet_id == outlet_b.id,
            MenuItem.name == "Isolation Test Item",
        )
        .first()
    )
    if menu_item is None:
        menu_item = MenuItem(
            outlet_id=outlet_b.id,
            category_id=category.id,
            name="Isolation Test Item",
            base_price=Decimal("100.00"),
            is_available=True,
            sort_order=0,
        )
        db.add(menu_item)
        db.flush()

    outlet_customer_a = (
        db.query(OutletCustomer)
        .filter(
            OutletCustomer.outlet_id == outlet_a.id,
            OutletCustomer.user_id == user.id,
        )
        .first()
    )
    baseline_orders = outlet_customer_a.total_orders if outlet_customer_a else None
    baseline_spend = (
        str(outlet_customer_a.total_spend) if outlet_customer_a else None
    )

    db.commit()

    return FixtureContext(
        outlet_a_id=outlet_a.id,
        outlet_a_slug=outlet_a.slug,
        outlet_b_id=outlet_b.id,
        outlet_b_slug=outlet_b.slug,
        user_id=user.id,
        menu_item_b_id=menu_item.id,
        baseline_a_orders=baseline_orders,
        baseline_a_spend=baseline_spend,
    )


def find_existing_test_order(db, user_id: UUID, outlet_b_id: UUID) -> UUID | None:
    row = (
        db.query(Order.id)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .filter(
            Order.user_id == user_id,
            Order.outlet_id == outlet_b_id,
            OrderItem.notes == ORDER_ITEM_NOTES,
        )
        .order_by(Order.created_at.desc())
        .first()
    )
    return row[0] if row else None


def extract_order_ids(payload) -> list[str]:
    if isinstance(payload, list):
        return [str(item["id"]) for item in payload]
    if isinstance(payload, dict) and "items" in payload:
        return [str(item["id"]) for item in payload["items"]]
    return []


def run_test_1(client: httpx.Client, ctx: FixtureContext, consumer_token: str, db) -> tuple[TestCaseResult, UUID]:
    existing = find_existing_test_order(db, ctx.user_id, ctx.outlet_b_id)
    if existing is not None:
        return (
            TestCaseResult(
                "Test 1: Consumer order at Outlet B",
                True,
                f"Reused existing isolation order {existing}",
            ),
            existing,
        )

    response = client.post(
        f"{BASE}/public/outlets/{ctx.outlet_b_slug}/orders",
        json={
            "order_type": OrderType.pickup.value,
            "items": [
                {
                    "menu_item_id": str(ctx.menu_item_b_id),
                    "quantity": 1,
                    "addon_ids": [],
                    "notes": ORDER_ITEM_NOTES,
                }
            ],
        },
        headers={"Authorization": f"Bearer {consumer_token}"},
    )
    if response.status_code != 201:
        return (
            TestCaseResult(
                "Test 1: Consumer order at Outlet B",
                False,
                f"Expected 201, got {response.status_code}: {response.text}",
            ),
            None,
        )

    body = response.json()
    order = body["order"]
    order_id = UUID(str(order["id"]))
    outlet_id = UUID(str(order["outlet_id"]))
    if outlet_id != ctx.outlet_b_id:
        return (
            TestCaseResult(
                "Test 1: Consumer order at Outlet B",
                False,
                f"Order outlet_id={outlet_id}, expected {ctx.outlet_b_id}",
            ),
            order_id,
        )

    return (
        TestCaseResult(
            "Test 1: Consumer order at Outlet B",
            True,
            f"Created order {order_id} at Outlet B",
        ),
        order_id,
    )


def run_test_2(
    client: httpx.Client,
    ctx: FixtureContext,
    staff_token: str,
    order_b_id: UUID,
) -> list[TestCaseResult]:
    results: list[TestCaseResult] = []
    headers = {"Authorization": f"Bearer {staff_token}"}

    orders_resp = client.get(
        f"{BASE}/outlets/{ctx.outlet_a_id}/orders",
        headers=headers,
    )
    if orders_resp.status_code != 200:
        results.append(
            TestCaseResult(
                "Test 2a: Outlet A orders exclude Outlet B order",
                False,
                f"Expected 200, got {orders_resp.status_code}: {orders_resp.text}",
            )
        )
    else:
        order_ids = extract_order_ids(orders_resp.json())
        leaked = str(order_b_id) in order_ids
        results.append(
            TestCaseResult(
                "Test 2a: Outlet A orders exclude Outlet B order",
                not leaked,
                (
                    f"Outlet B order {order_b_id} FOUND in Outlet A list: {order_ids}"
                    if leaked
                    else f"Outlet B order not in Outlet A list ({len(order_ids)} orders checked)"
                ),
            )
        )

    customers_resp = client.get(
        f"{BASE}/outlets/{ctx.outlet_a_id}/customers",
        headers=headers,
        params={"page": 1, "page_size": 100},
    )
    if customers_resp.status_code != 200:
        results.append(
            TestCaseResult(
                "Test 2b: Outlet A CRM stats not inflated by Outlet B",
                False,
                f"Expected 200, got {customers_resp.status_code}: {customers_resp.text}",
            )
        )
    else:
        items = customers_resp.json().get("items", [])
        match = next(
            (item for item in items if str(item.get("user_id")) == str(ctx.user_id)),
            None,
        )
        if match is None:
            results.append(
                TestCaseResult(
                    "Test 2b: Outlet A CRM stats not inflated by Outlet B",
                    True,
                    "User not listed in Outlet A CRM (no A-side patron record)",
                )
            )
        else:
            orders_ok = (
                ctx.baseline_a_orders is None
                or int(match["total_orders"]) == int(ctx.baseline_a_orders)
            )
            spend_ok = (
                ctx.baseline_a_spend is None
                or str(match["total_spend"]) == ctx.baseline_a_spend
            )
            passed = orders_ok and spend_ok
            results.append(
                TestCaseResult(
                    "Test 2b: Outlet A CRM stats not inflated by Outlet B",
                    passed,
                    (
                        f"CRM row total_orders={match['total_orders']} total_spend={match['total_spend']} "
                        f"(baseline orders={ctx.baseline_a_orders} spend={ctx.baseline_a_spend})"
                    ),
                )
            )

    detail_resp = client.get(
        f"{BASE}/outlets/{ctx.outlet_a_id}/customers/{ctx.user_id}",
        headers=headers,
    )
    if detail_resp.status_code == 404:
        results.append(
            TestCaseResult(
                "Test 2c: Outlet A customer detail is A-only or absent",
                True,
                "404 — no Outlet A patron relationship (expected if only ordered at B)",
            )
        )
    elif detail_resp.status_code == 200:
        detail = detail_resp.json()
        order_ids = [str(o["id"]) for o in detail.get("orders", [])]
        leaked = str(order_b_id) in order_ids
        results.append(
            TestCaseResult(
                "Test 2c: Outlet A customer detail is A-only or absent",
                not leaked,
                (
                    f"Outlet B order {order_b_id} appears in Outlet A customer detail orders: {order_ids}"
                    if leaked
                    else f"A-only detail OK ({len(order_ids)} orders at A)"
                ),
            )
        )
    else:
        results.append(
            TestCaseResult(
                "Test 2c: Outlet A customer detail is A-only or absent",
                False,
                f"Unexpected {detail_resp.status_code}: {detail_resp.text}",
            )
        )

    return results


def run_test_3(client: httpx.Client, ctx: FixtureContext, consumer_token: str) -> TestCaseResult:
    response = client.get(
        f"{BASE}/outlets/{ctx.outlet_a_id}/orders",
        headers={"Authorization": f"Bearer {consumer_token}"},
    )
    if response.status_code == 403:
        return TestCaseResult(
            "Test 3: Pure consumer token rejected on staff routes",
            True,
            "403 Forbidden as expected",
        )
    if response.status_code == 200:
        order_ids = extract_order_ids(response.json())
        return TestCaseResult(
            "Test 3: Pure consumer token rejected on staff routes",
            False,
            f"Got 200 with {len(order_ids)} orders — silent success/leak risk (expected 403)",
        )
    return TestCaseResult(
        "Test 3: Pure consumer token rejected on staff routes",
        False,
        f"Expected 403, got {response.status_code}: {response.text}",
    )


def run_test_4(client: httpx.Client, ctx: FixtureContext, staff_token: str) -> TestCaseResult:
    response = client.get(
        f"{BASE}/outlets/{ctx.outlet_b_id}/orders",
        headers={"Authorization": f"Bearer {staff_token}"},
    )
    if response.status_code == 403:
        return TestCaseResult(
            "Test 4: Outlet-A staff token rejected on Outlet B routes",
            True,
            "403 Forbidden as expected",
        )
    if response.status_code == 200:
        order_ids = extract_order_ids(response.json())
        return TestCaseResult(
            "Test 4: Outlet-A staff token rejected on Outlet B routes",
            False,
            f"Got 200 with {len(order_ids)} orders — cross-outlet staff access (expected 403)",
        )
    return TestCaseResult(
        "Test 4: Outlet-A staff token rejected on Outlet B routes",
        False,
        f"Expected 403, got {response.status_code}: {response.text}",
    )


def run_test_5(
    client: httpx.Client,
    consumer_token: str,
    order_b_id: UUID,
) -> TestCaseResult:
    response = client.get(
        f"{BASE}/public/users/me/orders",
        headers={"Authorization": f"Bearer {consumer_token}"},
    )
    if response.status_code != 200:
        return TestCaseResult(
            "Test 5: Consumer sees own cross-outlet order history",
            False,
            f"Expected 200, got {response.status_code}: {response.text}",
        )
    order_ids = [str(item["id"]) for item in response.json()]
    found = str(order_b_id) in order_ids
    return TestCaseResult(
        "Test 5: Consumer sees own cross-outlet order history",
        found,
        (
            f"Outlet B order {order_b_id} present in /public/users/me/orders"
            if found
            else f"Outlet B order missing from consumer history: {order_ids}"
        ),
    )


def print_results(results: list[TestCaseResult]) -> int:
    print("\nCross-outlet isolation audit")
    print("=" * 60)
    failures = 0
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.name}")
        print(f"       {result.detail}")
        if not result.passed:
            failures += 1
    print("=" * 60)
    if failures:
        print(f"FAILED — {failures} check(s) failed")
        return 1
    print("ALL PASSED — cross-outlet isolation verified")
    return 0


def main() -> None:
    db = SessionLocal()
    try:
        with httpx.Client(timeout=30.0) as client:
            health = client.get(f"{BASE}/health")
            if health.status_code != 200:
                raise SystemExit(
                    f"Backend not healthy at {BASE}/health ({health.status_code}). "
                    "Start the server with: python run.py"
                )

            ctx = ensure_fixtures(db)
            print("Fixtures ready:")
            print(f"  Outlet A: {ctx.outlet_a_slug} ({ctx.outlet_a_id})")
            print(f"  Outlet B: {ctx.outlet_b_slug} ({ctx.outlet_b_id})")
            print(f"  User U:   {ctx.user_id} phone={TEST_PHONE}")

            consumer_token = obtain_consumer_token(client, db, TEST_PHONE)
            payload = decode_jwt_payload(consumer_token)
            print(f"  Consumer token outlet_id: {payload.get('outlet_id')}")

            all_results: list[TestCaseResult] = []
            test1, order_b_id = run_test_1(client, ctx, consumer_token, db)
            all_results.append(test1)
            if order_b_id is None:
                print_results(all_results)
                raise SystemExit(1)

            staff_token = obtain_staff_token(client, db, TEST_PHONE, ctx.outlet_a_id)
            staff_payload = decode_jwt_payload(staff_token)
            print(f"  Staff token outlet_id:    {staff_payload.get('outlet_id')}")

            all_results.extend(run_test_2(client, ctx, staff_token, order_b_id))
            all_results.append(run_test_3(client, ctx, consumer_token))
            all_results.append(run_test_4(client, ctx, staff_token))
            all_results.append(run_test_5(client, consumer_token, order_b_id))

            raise SystemExit(print_results(all_results))
    finally:
        db.close()


if __name__ == "__main__":
    main()
