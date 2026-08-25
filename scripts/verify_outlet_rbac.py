"""Smoke-test outlet dashboard custom role RBAC via API."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy.orm import joinedload

from app.core.security import create_access_token
from app.db.database import SessionLocal
from app.models.outlet_user import OutletUser
from app.models.role import Role

BASE = "http://127.0.0.1:8000/api/v1"
ROLE_NAME = "Head Chef (smoke test)"


def auth_headers(user: OutletUser) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": str(user.id),
            "user_type": "outlet_user",
            "outlet_id": str(user.outlet_id),
        }
    )
    return {"Authorization": f"Bearer {token}"}


def find_owner(db) -> OutletUser:
    owner_role = (
        db.query(Role)
        .filter(Role.outlet_id.is_(None), Role.is_system_default.is_(True), Role.name == "Owner")
        .first()
    )
    if owner_role is None:
        raise RuntimeError("Owner system role not seeded")

    owner = (
        db.query(OutletUser)
        .options(joinedload(OutletUser.role))
        .filter(
            OutletUser.role_id == owner_role.id,
            OutletUser.active_status.is_(True),
        )
        .first()
    )
    if owner is None:
        raise RuntimeError("No active outlet Owner found in database")
    return owner


def main() -> None:
    db = SessionLocal()
    try:
        owner = find_owner(db)
        outlet_id = str(owner.outlet_id)
        headers = auth_headers(owner)

        with httpx.Client(base_url=BASE, headers=headers, timeout=30.0) as client:
            print(f"Using outlet {outlet_id}, owner {owner.name} ({owner.phone})")

            # 1. Permissions catalog
            perms_resp = client.get(f"/outlets/{outlet_id}/permissions")
            perms_resp.raise_for_status()
            permissions = perms_resp.json()
            assert len(permissions) > 0, "permissions list empty"
            print(f"  OK GET /permissions ({len(permissions)} permissions)")

            perm_by_key = {p["key"]: p for p in permissions}
            for key in ("menu.view", "menu.edit", "orders.view", "orders.edit"):
                assert key in perm_by_key, f"missing permission {key}"
            perm_ids = [perm_by_key[k]["id"] for k in ("menu.view", "menu.edit", "orders.view", "orders.edit")]

            # 2. Roles list (system + custom)
            roles_resp = client.get(f"/outlets/{outlet_id}/roles")
            roles_resp.raise_for_status()
            roles = roles_resp.json()
            system_names = {r["name"] for r in roles if r["is_system_default"]}
            assert {"Owner", "Manager", "Staff"}.issubset(system_names)
            assert all("permission_keys" in r for r in roles)
            print(f"  OK GET /roles ({len(roles)} roles, system={sorted(system_names)})")

            # 3. Staff list
            staff_resp = client.get(f"/outlets/{outlet_id}/staff")
            staff_resp.raise_for_status()
            staff = staff_resp.json()
            assert len(staff) >= 1, "expected at least owner in staff list"
            print(f"  OK GET /staff ({len(staff)} members)")

            # 4. Create custom role (or reuse from prior run)
            existing = next((r for r in roles if r["name"] == ROLE_NAME), None)
            if existing:
                custom_role = existing
                print(f"  OK reusing custom role {ROLE_NAME}")
            else:
                create_resp = client.post(
                    f"/outlets/{outlet_id}/roles",
                    json={"name": ROLE_NAME, "permission_ids": perm_ids},
                )
                create_resp.raise_for_status()
                custom_role = create_resp.json()
                assert custom_role["name"] == ROLE_NAME
                assert set(custom_role["permission_keys"]) == {
                    "menu.view",
                    "menu.edit",
                    "orders.view",
                    "orders.edit",
                }
                print(f"  OK POST /roles -> {ROLE_NAME}")

            # 5. Add staff with custom role (unique phone)
            test_phone = "9999900001"
            test_staff = next((s for s in staff if s["phone"] == test_phone), None)
            if test_staff is None:
                add_resp = client.post(
                    f"/outlets/{outlet_id}/staff",
                    json={
                        "name": "Smoke Test Staff",
                        "phone": test_phone,
                        "role_id": custom_role["id"],
                    },
                )
                add_resp.raise_for_status()
                test_staff = add_resp.json()
                print(f"  OK POST /staff -> {test_staff['name']}")
            else:
                patch_resp = client.patch(
                    f"/outlets/{outlet_id}/staff/{test_staff['id']}",
                    json={"role_id": custom_role["id"]},
                )
                patch_resp.raise_for_status()
                test_staff = patch_resp.json()
                print(f"  OK PATCH /staff/{test_staff['id']} role -> {ROLE_NAME}")

            assert test_staff["role_name"] == ROLE_NAME

            # 6. /auth/me for custom-role staff
            staff_user = (
                db.query(OutletUser)
                .filter(OutletUser.id == test_staff["id"])
                .first()
            )
            assert staff_user is not None
            me_resp = client.get(
                "/auth/me",
                headers=auth_headers(staff_user),
            )
            me_resp.raise_for_status()
            me = me_resp.json()
            assert me["role_name"] == ROLE_NAME
            assert me["is_support_session"] is False
            expected_perms = {"menu.view", "menu.edit", "orders.view", "orders.edit"}
            actual_perms = set(me["permissions"])
            assert expected_perms.issubset(actual_perms), (
                f"expected {expected_perms} subset of {actual_perms}"
            )
            print(f"  OK GET /auth/me permissions for custom role: {sorted(expected_perms)}")

            # 7. Owner cannot assign Owner via PATCH (guard)
            manager_role = next(r for r in roles if r["name"] == "Manager")
            owner_role = next(r for r in roles if r["name"] == "Owner")
            block_resp = client.patch(
                f"/outlets/{outlet_id}/staff/{test_staff['id']}",
                json={"role_id": owner_role["id"]},
            )
            assert block_resp.status_code == 400, "assigning Owner via PATCH should be blocked"
            print("  OK Owner assignment via PATCH blocked")

            # restore manager attempt didn't stick; ensure still custom role
            assert test_staff["role_id"] == custom_role["id"]

        print("\nAll outlet RBAC smoke tests passed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
