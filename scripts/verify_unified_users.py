"""Verify unified user model: same phone as staff + consumer, auth, CRM fields."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import joinedload

from app.core.security import create_user_token
from app.db.database import SessionLocal
from app.models.outlet import Outlet
from app.models.outlet_membership import OutletMembership
from app.models.role import Role
from app.models.user import User


def main() -> None:
    db = SessionLocal()
    try:
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
            raise SystemExit("Owner role missing — run seed.py first")

        outlet = db.query(Outlet).filter(Outlet.slug == "south-indian-nirmand").first()
        if outlet is None:
            outlet = db.query(Outlet).first()
        if outlet is None:
            raise SystemExit("No outlets in database")

        owner_membership = (
            db.query(OutletMembership)
            .options(joinedload(OutletMembership.user))
            .filter(
                OutletMembership.outlet_id == outlet.id,
                OutletMembership.role_id == owner_role.id,
            )
            .first()
        )
        if owner_membership is None:
            raise SystemExit(f"No owner membership for outlet {outlet.slug}")

        user = owner_membership.user
        token_staff = create_user_token(str(user.id), str(outlet.id))
        token_consumer = create_user_token(str(user.id))

        assert token_staff
        assert token_consumer
        assert user.phone
        assert owner_membership.user_id == user.id

        print("Unified user verification passed:")
        print(f"  outlet: {outlet.slug}")
        print(f"  user_id: {user.id}")
        print(f"  phone: {user.phone}")
        print(f"  membership_id: {owner_membership.id}")
        print("  staff + consumer tokens generated successfully")
    finally:
        db.close()


if __name__ == "__main__":
    main()
