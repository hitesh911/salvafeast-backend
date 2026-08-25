"""In-process subscription API smoke test."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.db.database import SessionLocal
from app.main import app
from app.models.enums import SubscriptionStatus
from app.models.outlet_subscription import OutletSubscription
from app.models.outlet_user import OutletUser
from app.models.role import Role

db = SessionLocal()
try:
    owner_role = (
        db.query(Role)
        .filter(Role.name == "Owner", Role.is_system_default.is_(True))
        .first()
    )
    owner = db.query(OutletUser).filter(OutletUser.role_id == owner_role.id).first()
    assert owner is not None
    outlet_id = owner.outlet_id
    sub = (
        db.query(OutletSubscription)
        .filter(OutletSubscription.outlet_id == outlet_id)
        .first()
    )
    if sub and sub.status == SubscriptionStatus.cancelled:
        sub.status = SubscriptionStatus.active
        db.commit()

    token = create_access_token(
        {
            "sub": str(owner.id),
            "user_type": "outlet_user",
            "outlet_id": str(outlet_id),
        }
    )
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get(f"/api/v1/outlets/{outlet_id}/subscription", headers=headers).status_code == 200
    assert (
        client.get(f"/api/v1/outlets/{outlet_id}/subscription/invoices", headers=headers).status_code
        == 200
    )

    detail = client.get(f"/api/v1/outlets/{outlet_id}/subscription", headers=headers).json()
    if detail["status"] != "cancelled":
        cancel = client.post(
            f"/api/v1/outlets/{outlet_id}/subscription/cancel", headers=headers
        )
        assert cancel.status_code == 200
        assert cancel.json()["status"] == "cancelled"
        dup = client.post(
            f"/api/v1/outlets/{outlet_id}/subscription/cancel", headers=headers
        )
        assert dup.status_code == 409

    print("In-process subscription smoke tests passed.")
finally:
    db.close()
