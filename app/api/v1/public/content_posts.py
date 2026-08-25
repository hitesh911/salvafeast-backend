from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.public.deps import require_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.content_post import (
    ContentPostCreateRequest,
    ContentPostLikeResponse,
    ContentPostReportRequest,
    ContentPostResponse,
    PaginatedContentPostFeed,
)
from app.services.content_posts import (
    create_content_post,
    create_report,
    get_feed,
    to_content_post_response,
    toggle_like,
)

router = APIRouter(prefix="/content-posts", tags=["public-content-posts"])


@router.post("", response_model=ContentPostResponse, status_code=status.HTTP_201_CREATED)
def create_post(
    payload: ContentPostCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> ContentPostResponse:
    post, outlet = create_content_post(db, user, payload)
    return to_content_post_response(post, db, outlet)


@router.get("/feed", response_model=PaginatedContentPostFeed)
def feed(
    lat: float | None = Query(default=None),
    lng: float | None = Query(default=None),
    city_search: str | None = Query(default=None, min_length=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> PaginatedContentPostFeed:
    if (lat is None) != (lng is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both lat and lng must be provided together",
        )
    return get_feed(
        db,
        user,
        lat=lat,
        lng=lng,
        city_search=city_search,
        page=page,
        page_size=page_size,
    )


@router.post("/{post_id}/like", response_model=ContentPostLikeResponse)
def like_post(
    post_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> ContentPostLikeResponse:
    return toggle_like(db, user, post_id)


@router.post("/{post_id}/report", status_code=status.HTTP_204_NO_CONTENT)
def report_post(
    post_id: UUID,
    payload: ContentPostReportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> None:
    create_report(db, user, post_id, payload.reason)
