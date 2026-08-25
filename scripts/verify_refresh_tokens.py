"""Verify refresh token issue, rotation, logout, and rejection flows."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException
from sqlalchemy.orm import joinedload

from app.db.database import SessionLocal
from app.models.outlet import Outlet
from app.models.outlet_membership import OutletMembership
from app.models.platform_admin import PlatformAdmin
from app.models.role import Role
from app.services.refresh_tokens import issue_tokens, refresh_session, revoke_refresh_token


def _assert_raises(fn, label: str) -> None:
    try:
        fn()
    except HTTPException:
        return
    except Exception as exc:
        raise SystemExit(f"{label}: unexpected error {exc}") from exc
    raise SystemExit(f"{label}: expected failure but succeeded")


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

        user_pair = issue_tokens(
            db,
            session_kind="user",
            subject_id=user.id,
            outlet_id=outlet.id,
        )
        assert user_pair.access_token
        assert user_pair.refresh_token
        assert user_pair.expires_in > 0

        old_refresh = user_pair.refresh_token
        rotated = refresh_session(db, old_refresh)
        assert rotated.access_token
        assert rotated.refresh_token != old_refresh

        _assert_raises(
            lambda: refresh_session(db, old_refresh),
            "rotated refresh token reuse",
        )

        revoke_refresh_token(db, rotated.refresh_token)
        _assert_raises(
            lambda: refresh_session(db, rotated.refresh_token),
            "revoked refresh token",
        )

        platform_admin = (
            db.query(PlatformAdmin).filter(PlatformAdmin.active_status.is_(True)).first()
        )
        if platform_admin:
            admin_pair = issue_tokens(
                db,
                session_kind="platform_admin",
                subject_id=platform_admin.id,
            )
            admin_rotated = refresh_session(db, admin_pair.refresh_token)
            assert admin_rotated.access_token

            support_pair = issue_tokens(
                db,
                session_kind="platform_support",
                subject_id=platform_admin.id,
                outlet_id=outlet.id,
                session_meta={
                    "platform_admin_id": str(platform_admin.id),
                    "permissions": ["orders.view"],
                },
            )
            support_rotated = refresh_session(db, support_pair.refresh_token)
            assert support_rotated.access_token

        print("Refresh token verification passed:")
        print(f"  user_id: {user.id}")
        print(f"  outlet: {outlet.slug}")
        print("  user issue -> rotate -> reject reuse -> revoke -> reject revoked")
        if platform_admin:
            print("  platform_admin + platform_support refresh verified")
    finally:
        db.close()


if __name__ == "__main__":
    main()
