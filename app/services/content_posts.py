from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.embed_urls import InvalidEmbedUrlError, detect_embed_platform
from app.models.content_post import ContentPost
from app.models.content_post_like import ContentPostLike
from app.models.content_post_report import ContentPostReport
from app.models.menu_item import MenuItem
from app.models.outlet import Outlet
from app.models.user import User
from app.models.enums import VerificationStatus
from app.schemas.content_post import (
    ContentPostCreateRequest,
    ContentPostFeedItem,
    ContentPostLikeResponse,
    ContentPostMenuItemSummary,
    ContentPostOutletSummary,
    ContentPostResponse,
    PaginatedContentPostFeed,
    PaginatedPlatformContentPosts,
    PlatformContentPostListItem,
    PlatformContentPostSort,
)

EARTH_RADIUS_KM = 6371.0


def _build_outlet_summary(outlet: Outlet) -> ContentPostOutletSummary:
    return ContentPostOutletSummary(
        id=outlet.id,
        name=outlet.name,
        slug=outlet.slug,
        logo_url=outlet.logo_url,
        verification_status=outlet.verification_status,
    )


def _build_menu_item_summary(menu_item: MenuItem | None) -> ContentPostMenuItemSummary | None:
    if menu_item is None:
        return None
    return ContentPostMenuItemSummary(
        id=menu_item.id,
        name=menu_item.name,
        base_price=menu_item.base_price,
    )


def _to_content_post_response(post: ContentPost, outlet: Outlet) -> ContentPostResponse:
    return ContentPostResponse(
        id=post.id,
        created_by_user_id=post.created_by_user_id,
        outlet_id=post.outlet_id,
        menu_item_id=post.menu_item_id,
        embed_url=post.embed_url,
        embed_platform=post.embed_platform,
        caption=post.caption,
        like_count=post.like_count,
        report_count=post.report_count,
        is_hidden=post.is_hidden,
        created_at=post.created_at,
        outlet_verification_status=outlet.verification_status,
    )


def _haversine_km_expr(lat: float, lng: float):
    lat_rad = func.radians(Outlet.latitude - lat)
    lng_rad = func.radians(Outlet.longitude - lng)
    a = (
        func.pow(func.sin(lat_rad / 2), 2)
        + func.cos(func.radians(lat))
        * func.cos(func.radians(Outlet.latitude))
        * func.pow(func.sin(lng_rad / 2), 2)
    )
    return EARTH_RADIUS_KM * 2 * func.asin(func.sqrt(a))


def create_content_post(
    db: Session, user: User, payload: ContentPostCreateRequest
) -> tuple[ContentPost, Outlet]:
    outlet = db.query(Outlet).filter(Outlet.id == payload.outlet_id).first()
    if outlet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outlet not found")
    if not outlet.active_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Outlet is not active",
        )

    if payload.menu_item_id is not None:
        menu_item = (
            db.query(MenuItem).filter(MenuItem.id == payload.menu_item_id).first()
        )
        if menu_item is None or menu_item.outlet_id != outlet.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Menu item does not belong to this outlet",
            )

    try:
        embed_platform = detect_embed_platform(payload.embed_url)
    except InvalidEmbedUrlError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    post = ContentPost(
        created_by_user_id=user.id,
        outlet_id=payload.outlet_id,
        menu_item_id=payload.menu_item_id,
        embed_url=payload.embed_url.strip(),
        embed_platform=embed_platform,
        caption=payload.caption,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post, outlet


def _liked_post_ids(db: Session, user_id: UUID, post_ids: list[UUID]) -> set[UUID]:
    if not post_ids:
        return set()
    rows = (
        db.query(ContentPostLike.content_post_id)
        .filter(
            ContentPostLike.user_id == user_id,
            ContentPostLike.content_post_id.in_(post_ids),
        )
        .all()
    )
    return {row[0] for row in rows}


def get_feed(
    db: Session,
    user: User,
    *,
    lat: float | None,
    lng: float | None,
    city_search: str | None,
    page: int,
    page_size: int,
) -> PaginatedContentPostFeed:
    base_filters = [
        ContentPost.is_hidden.is_(False),
        Outlet.active_status.is_(True),
        Outlet.verification_status == VerificationStatus.verified,
    ]

    distance_expr = None
    if lat is not None and lng is not None:
        base_filters.extend(
            [
                Outlet.latitude.isnot(None),
                Outlet.longitude.isnot(None),
            ]
        )
        distance_expr = _haversine_km_expr(lat, lng).label("distance_km")
        query = (
            db.query(ContentPost, distance_expr)
            .join(Outlet, ContentPost.outlet_id == Outlet.id)
            .filter(*base_filters)
            .options(
                joinedload(ContentPost.outlet),
                joinedload(ContentPost.menu_item),
            )
            .order_by(distance_expr.asc(), ContentPost.created_at.desc())
        )
    elif city_search:
        query = (
            db.query(ContentPost)
            .join(Outlet, ContentPost.outlet_id == Outlet.id)
            .filter(*base_filters, Outlet.address.ilike(f"%{city_search}%"))
            .options(
                joinedload(ContentPost.outlet),
                joinedload(ContentPost.menu_item),
            )
            .order_by(ContentPost.created_at.desc())
        )
    else:
        query = (
            db.query(ContentPost)
            .join(Outlet, ContentPost.outlet_id == Outlet.id)
            .filter(*base_filters)
            .options(
                joinedload(ContentPost.outlet),
                joinedload(ContentPost.menu_item),
            )
            .order_by(ContentPost.created_at.desc())
        )

    count_query = (
        db.query(func.count(ContentPost.id))
        .join(Outlet, ContentPost.outlet_id == Outlet.id)
        .filter(*base_filters)
    )
    if city_search and (lat is None or lng is None):
        count_query = count_query.filter(Outlet.address.ilike(f"%{city_search}%"))

    total = count_query.scalar() or 0
    offset = (page - 1) * page_size
    rows = query.offset(offset).limit(page_size).all()

    if lat is not None and lng is not None:
        posts_with_distance = rows
        post_ids = [row[0].id for row in posts_with_distance]
        liked_ids = _liked_post_ids(db, user.id, post_ids)
        items = [
            ContentPostFeedItem(
                id=post.id,
                created_by_user_id=post.created_by_user_id,
                embed_url=post.embed_url,
                embed_platform=post.embed_platform,
                caption=post.caption,
                like_count=post.like_count,
                created_at=post.created_at,
                outlet=_build_outlet_summary(post.outlet),
                menu_item=_build_menu_item_summary(post.menu_item),
                distance_km=float(distance_km) if distance_km is not None else None,
                has_current_user_liked=post.id in liked_ids,
            )
            for post, distance_km in posts_with_distance
        ]
    else:
        posts = rows
        post_ids = [post.id for post in posts]
        liked_ids = _liked_post_ids(db, user.id, post_ids)
        items = [
            ContentPostFeedItem(
                id=post.id,
                created_by_user_id=post.created_by_user_id,
                embed_url=post.embed_url,
                embed_platform=post.embed_platform,
                caption=post.caption,
                like_count=post.like_count,
                created_at=post.created_at,
                outlet=_build_outlet_summary(post.outlet),
                menu_item=_build_menu_item_summary(post.menu_item),
                distance_km=None,
                has_current_user_liked=post.id in liked_ids,
            )
            for post in posts
        ]

    return PaginatedContentPostFeed(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


def _get_visible_post(db: Session, post_id: UUID) -> ContentPost:
    post = (
        db.query(ContentPost)
        .filter(ContentPost.id == post_id, ContentPost.is_hidden.is_(False))
        .first()
    )
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


def toggle_like(db: Session, user: User, post_id: UUID) -> ContentPostLikeResponse:
    post = (
        db.query(ContentPost)
        .filter(ContentPost.id == post_id, ContentPost.is_hidden.is_(False))
        .with_for_update()
        .first()
    )
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    existing = (
        db.query(ContentPostLike)
        .filter(
            ContentPostLike.content_post_id == post_id,
            ContentPostLike.user_id == user.id,
        )
        .first()
    )

    if existing is None:
        db.add(ContentPostLike(content_post_id=post_id, user_id=user.id))
        post.like_count += 1
        liked = True
    else:
        db.delete(existing)
        post.like_count = max(post.like_count - 1, 0)
        liked = False

    db.commit()
    db.refresh(post)
    return ContentPostLikeResponse(liked=liked, like_count=post.like_count)


def create_report(
    db: Session, user: User, post_id: UUID, reason: str | None
) -> None:
    post = _get_visible_post(db, post_id)
    db.add(
        ContentPostReport(
            content_post_id=post.id,
            reported_by_user_id=user.id,
            reason=reason,
        )
    )
    post.report_count += 1
    db.commit()


def list_posts_for_moderation(
    db: Session,
    *,
    sort: PlatformContentPostSort,
    page: int,
    page_size: int,
) -> PaginatedPlatformContentPosts:
    query = db.query(ContentPost).options(joinedload(ContentPost.outlet))

    if sort == "most_reported":
        query = query.order_by(ContentPost.report_count.desc(), ContentPost.created_at.desc())
    else:
        query = query.order_by(ContentPost.created_at.desc())

    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()

    items = [
        PlatformContentPostListItem(
            id=post.id,
            embed_url=post.embed_url,
            embed_platform=post.embed_platform,
            caption=post.caption,
            like_count=post.like_count,
            report_count=post.report_count,
            is_hidden=post.is_hidden,
            created_at=post.created_at,
            outlet_id=post.outlet_id,
            outlet_name=post.outlet.name,
            created_by_user_id=post.created_by_user_id,
        )
        for post in rows
    ]

    return PaginatedPlatformContentPosts(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


def hide_post(db: Session, post_id: UUID) -> ContentPost:
    post = db.query(ContentPost).filter(ContentPost.id == post_id).first()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    post.is_hidden = True
    db.commit()
    db.refresh(post)
    return post


def to_content_post_response(
    post: ContentPost, db: Session, outlet: Outlet | None = None
) -> ContentPostResponse:
    if outlet is None:
        outlet = db.query(Outlet).filter(Outlet.id == post.outlet_id).first()
    if outlet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outlet not found")
    return _to_content_post_response(post, outlet)
