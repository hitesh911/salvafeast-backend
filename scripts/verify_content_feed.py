"""Verify content feed embed detection, CRUD flows, likes, reports, and moderation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException

from app.core.embed_urls import InvalidEmbedUrlError, detect_embed_platform
from app.db.database import SessionLocal
from app.models.content_post import ContentPost
from app.models.content_post_like import ContentPostLike
from app.models.enums import EmbedPlatform, VerificationStatus
from app.models.outlet import Outlet
from app.models.user import User
from app.schemas.content_post import ContentPostCreateRequest
from app.services.content_posts import (
    create_content_post,
    create_report,
    get_feed,
    hide_post,
    list_posts_for_moderation,
    to_content_post_response,
    toggle_like,
)


def _assert_raises(fn, exc_type, label: str) -> None:
    try:
        fn()
    except exc_type:
        return
    except Exception as exc:
        raise SystemExit(f"{label}: unexpected error {exc}") from exc
    raise SystemExit(f"{label}: expected failure but succeeded")


def main() -> None:
    assert detect_embed_platform("https://www.instagram.com/p/ABC123/") == EmbedPlatform.instagram
    assert detect_embed_platform("https://instagram.com/reel/xyz/") == EmbedPlatform.instagram
    assert detect_embed_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == EmbedPlatform.youtube
    assert detect_embed_platform("https://youtu.be/dQw4w9WgXcQ") == EmbedPlatform.youtube
    _assert_raises(
        lambda: detect_embed_platform("https://example.com/video"),
        InvalidEmbedUrlError,
        "unsupported embed URL",
    )
    print("  embed URL detection OK")

    db = SessionLocal()
    try:
        outlet = db.query(Outlet).filter(Outlet.active_status.is_(True)).first()
        if outlet is None:
            raise SystemExit("No active outlet in database — run seed.py first")

        user = db.query(User).first()
        if user is None:
            raise SystemExit("No users in database — run seed.py first")

        outlet.latitude = 31.1048
        outlet.longitude = 77.1734
        outlet.verification_status = VerificationStatus.verified
        if outlet.address is None:
            outlet.address = "Shimla, Himachal Pradesh"
        db.commit()

        _assert_raises(
            lambda: create_content_post(
                db,
                user,
                ContentPostCreateRequest(
                    outlet_id=outlet.id,
                    embed_url="https://tiktok.com/@user/video/1",
                ),
            ),
            HTTPException,
            "invalid embed URL on create",
        )
        print("  invalid embed URL rejected on create")

        post_a, _ = create_content_post(
            db,
            user,
            ContentPostCreateRequest(
                outlet_id=outlet.id,
                embed_url="https://www.instagram.com/p/TESTPOST1/",
                caption="Test post A",
            ),
        )
        post_b, _ = create_content_post(
            db,
            user,
            ContentPostCreateRequest(
                outlet_id=outlet.id,
                embed_url="https://www.youtube.com/watch?v=test123",
                caption="Test post B",
            ),
        )
        assert post_a.embed_platform == EmbedPlatform.instagram
        assert post_b.embed_platform == EmbedPlatform.youtube
        print("  content posts created")

        outlet.verification_status = VerificationStatus.pending
        db.commit()

        pending_post, pending_outlet = create_content_post(
            db,
            user,
            ContentPostCreateRequest(
                outlet_id=outlet.id,
                embed_url="https://www.instagram.com/p/PENDINGPOST/",
                caption="Pending outlet post",
            ),
        )
        pending_response = to_content_post_response(pending_post, db, pending_outlet)
        assert pending_response.outlet_verification_status == VerificationStatus.pending
        feed_pending = get_feed(db, user, lat=None, lng=None, city_search=None, page=1, page_size=100)
        pending_ids = {item.id for item in feed_pending.items}
        assert pending_post.id not in pending_ids
        print("  pending outlet post excluded from feed OK")

        outlet.verification_status = VerificationStatus.verified
        db.commit()
        feed_after_verify = get_feed(
            db, user, lat=None, lng=None, city_search=None, page=1, page_size=100
        )
        verified_ids = {item.id for item in feed_after_verify.items}
        assert pending_post.id in verified_ids
        print("  verified outlet post appears in feed OK")

        feed_fallback = get_feed(db, user, lat=None, lng=None, city_search=None, page=1, page_size=20)
        assert feed_fallback.total >= 2
        feed_ids = [item.id for item in feed_fallback.items]
        assert post_b.id in feed_ids or post_a.id in feed_ids
        print("  feed fallback OK")

        feed_geo = get_feed(
            db, user, lat=31.1048, lng=77.1734, city_search=None, page=1, page_size=20
        )
        assert all(item.distance_km is not None for item in feed_geo.items)
        assert all(
            item.outlet.verification_status == VerificationStatus.verified
            for item in feed_geo.items
        )
        print("  feed geo distance OK")

        feed_city = get_feed(
            db, user, lat=None, lng=None, city_search="Shimla", page=1, page_size=20
        )
        assert feed_city.total >= 1
        print("  feed city_search OK")

        like_first = toggle_like(db, user, post_a.id)
        assert like_first.liked is True
        assert like_first.like_count == 1

        like_second = toggle_like(db, user, post_a.id)
        assert like_second.liked is False
        assert like_second.like_count == 0
        print("  like toggle OK")

        for _ in range(3):
            create_report(db, user, post_b.id, reason="spam")
        db.refresh(post_b)
        refreshed = db.query(ContentPost).filter(ContentPost.id == post_b.id).first()
        assert refreshed is not None
        assert refreshed.report_count == 3
        assert refreshed.is_hidden is False
        print("  report increments without auto-hide OK")

        moderation = list_posts_for_moderation(
            db, sort="most_reported", page=1, page_size=20
        )
        assert moderation.items[0].id == post_b.id
        assert moderation.items[0].report_count == 3
        print("  moderation sort OK")

        hide_post(db, post_b.id)
        feed_after_hide = get_feed(
            db, user, lat=None, lng=None, city_search=None, page=1, page_size=100
        )
        hidden_ids = {item.id for item in feed_after_hide.items}
        assert post_b.id not in hidden_ids
        print("  hide excludes from feed OK")

        db.query(ContentPostLike).filter(
            ContentPostLike.content_post_id.in_(
                [post_a.id, post_b.id, pending_post.id]
            )
        ).delete(synchronize_session=False)
        db.query(ContentPost).filter(
            ContentPost.id.in_([post_a.id, post_b.id, pending_post.id])
        ).delete(synchronize_session=False)
        db.commit()

        print("Content feed verification passed:")
        print(f"  outlet: {outlet.slug}")
        print(f"  user_id: {user.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
