"""Smoke-test outlet subscription cancel API."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy.orm import joinedload

from app.core.security import create_access_token
from app.db.database import SessionLocal
from app.models.enums import SubscriptionStatus
from app.models.outlet_user import OutletUser
from app.models.role import Role

BASE = "http://127.0.0.1:8000/api/v1"


def auth_headers(user: OutletUser) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": str(user.id),
            "user_type": "outlet_user",
            "outlet_id": str(user.outlet_id),
        }
    )
    return {"Authorization": f"Bearer {token}"}


def main() -> None:
    db = SessionLocal()
    try:
        owner_role = (
            db.query(Role)
            .filter(Role.outlet_id.is_(None), Role.name == "Owner", Role.is_system_default.is_(True))
            .first()
        )
        owner = (
            db.query(OutletUser)
            .options(joinedload(OutletUser.role))
            .filter(OutletUser.role_id == owner_role.id, OutletUser.active_status.is_(True))
            .first()
        )
        if owner is None:
            raise RuntimeError("No owner found")

        outlet_id = str(owner.outlet_id)
        headers = auth_headers(owner)

        with httpx.Client(base_url=BASE, headers=headers, timeout=30.0) as client:
            sub_resp = client.get(f"/outlets/{outlet_id}/subscription")
            sub_resp.raise_for_status()
            print(f"  OK GET subscription status={sub_resp.json()['status']}")

            inv_resp = client.get(f"/outlets/{outlet_id}/subscription/invoices")
            inv_resp.raise_for_status()
            print(f"  OK GET invoices ({len(inv_resp.json())} items)")

            if sub_resp.json()["status"] != "cancelled":
                cancel_resp = client.post(f"/outlets/{outlet_id}/subscription/cancel")
                cancel_resp.raise_for_status()
                assert cancel_resp.json()["status"] == "cancelled"
                print("  OK POST cancel -> cancelled")

                dup_resp = client.post(f"/outlets/{outlet_id}/subscription/cancel")
                assert dup_resp.status_code == 409
                print("  OK duplicate cancel blocked")
            else:
                print("  OK subscription already cancelled")

        print("\nSubscription smoke tests passed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
