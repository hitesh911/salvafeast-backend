from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.v1.deps import require_outlet_permission
from app.core.gcs import (
    generate_menu_image_upload_url,
    upload_bytes_to_gcs,
    verify_local_menu_upload_token,
)
from app.db.database import get_db
from app.models.menu_category import MenuCategory
from app.models.menu_item import MenuItem
from app.models.menu_item_addon import MenuItemAddon
from app.models.menu_item_image import MenuItemImage
from app.models.menu_item_variant import MenuItemVariant
from app.models.order_item import OrderItem
from app.models.order_item_addon import OrderItemAddon
from app.schemas.menu import (
    MenuCategoryCreate,
    MenuCategoryResponse,
    MenuCategoryUpdate,
    MenuImageUploadUrlRequest,
    MenuImageUploadUrlResponse,
    MenuItemAddonCreate,
    MenuItemAddonResponse,
    MenuItemAddonUpdate,
    MenuItemAvailabilityUpdate,
    MenuItemCreate,
    MenuItemDetailResponse,
    MenuItemImageCreate,
    MenuItemImageResponse,
    MenuItemResponse,
    MenuItemUpdate,
    MenuItemVariantCreate,
    MenuItemVariantResponse,
    MenuItemVariantUpdate,
)

router = APIRouter(prefix="/outlets/{outlet_id}", tags=["menu"])


def _get_category(db: Session, outlet_id: UUID, category_id: UUID) -> MenuCategory:
    category = (
        db.query(MenuCategory)
        .filter(MenuCategory.id == category_id, MenuCategory.outlet_id == outlet_id)
        .first()
    )
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


def _get_item(db: Session, outlet_id: UUID, item_id: UUID) -> MenuItem:
    item = (
        db.query(MenuItem)
        .filter(MenuItem.id == item_id, MenuItem.outlet_id == outlet_id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found")
    return item


def _ensure_variant_price_non_negative(base_price: Decimal, price_delta: Decimal) -> None:
    if base_price + price_delta < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Variant price cannot be below ₹0 (base price + adjustment)",
        )


def _get_item_detail(db: Session, outlet_id: UUID, item_id: UUID) -> MenuItem:
    item = (
        db.query(MenuItem)
        .options(
            selectinload(MenuItem.images),
            selectinload(MenuItem.variants),
            selectinload(MenuItem.addons),
        )
        .filter(MenuItem.id == item_id, MenuItem.outlet_id == outlet_id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found")
    return item


def _get_image(db: Session, item_id: UUID, image_id: UUID) -> MenuItemImage:
    image = (
        db.query(MenuItemImage)
        .filter(MenuItemImage.id == image_id, MenuItemImage.menu_item_id == item_id)
        .first()
    )
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return image


def _get_variant(db: Session, item_id: UUID, variant_id: UUID) -> MenuItemVariant:
    variant = (
        db.query(MenuItemVariant)
        .filter(MenuItemVariant.id == variant_id, MenuItemVariant.menu_item_id == item_id)
        .first()
    )
    if variant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
    return variant


def _get_addon(db: Session, item_id: UUID, addon_id: UUID) -> MenuItemAddon:
    addon = (
        db.query(MenuItemAddon)
        .filter(MenuItemAddon.id == addon_id, MenuItemAddon.menu_item_id == item_id)
        .first()
    )
    if addon is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Addon not found")
    return addon


def _raise_if_referenced(in_use: bool, message: str) -> None:
    if in_use:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def _safe_delete(db: Session, entity: object, conflict_message: str) -> None:
    db.delete(entity)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=conflict_message,
        ) from None


@router.post(
    "/menu-images/upload-url",
    response_model=MenuImageUploadUrlResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_menu_image_upload_url(
    outlet_id: UUID,
    payload: MenuImageUploadUrlRequest,
    _user=Depends(require_outlet_permission("menu.edit")),
):
    upload_url, image_url = generate_menu_image_upload_url(
        outlet_id, payload.filename, payload.content_type
    )
    return MenuImageUploadUrlResponse(upload_url=upload_url, image_url=image_url)


@router.put("/menu-images/local-upload")
async def upload_menu_image_locally(
    outlet_id: UUID,
    request: Request,
    token: str = Query(min_length=1),
):
    blob_name, content_type = verify_local_menu_upload_token(outlet_id, token)
    data = await request.body()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty upload body")
    upload_bytes_to_gcs(blob_name, data, content_type)
    return {"ok": True}


@router.get("/menu/categories", response_model=list[MenuCategoryResponse])
def list_categories(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("menu.view")),
):
    categories = (
        db.query(MenuCategory)
        .filter(MenuCategory.outlet_id == outlet_id)
        .order_by(MenuCategory.sort_order, MenuCategory.name)
        .all()
    )
    return categories


@router.post(
    "/menu/categories",
    response_model=MenuCategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    outlet_id: UUID,
    payload: MenuCategoryCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("menu.edit")),
):
    category = MenuCategory(
        outlet_id=outlet_id,
        name=payload.name,
        sort_order=payload.sort_order,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.patch("/menu/categories/{category_id}", response_model=MenuCategoryResponse)
def update_category(
    outlet_id: UUID,
    category_id: UUID,
    payload: MenuCategoryUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("menu.edit")),
):
    category = _get_category(db, outlet_id, category_id)
    if payload.name is not None:
        category.name = payload.name
    if payload.sort_order is not None:
        category.sort_order = payload.sort_order
    db.commit()
    db.refresh(category)
    return category


@router.delete("/menu/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    outlet_id: UUID,
    category_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("menu.edit")),
):
    category = _get_category(db, outlet_id, category_id)
    db.delete(category)
    db.commit()


@router.get("/menu/items", response_model=list[MenuItemResponse])
def list_items(
    outlet_id: UUID,
    category_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("menu.view")),
):
    query = db.query(MenuItem).filter(MenuItem.outlet_id == outlet_id)
    if category_id is not None:
        query = query.filter(MenuItem.category_id == category_id)
    items = query.order_by(MenuItem.sort_order, MenuItem.name).all()
    return items


@router.get("/menu/items/{item_id}", response_model=MenuItemDetailResponse)
def get_item(
    outlet_id: UUID,
    item_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("menu.view")),
):
    item = _get_item_detail(db, outlet_id, item_id)
    return MenuItemDetailResponse(
        **MenuItemResponse.model_validate(item).model_dump(),
        images=[MenuItemImageResponse.model_validate(img) for img in item.images],
        variants=[MenuItemVariantResponse.model_validate(v) for v in item.variants],
        addons=[MenuItemAddonResponse.model_validate(a) for a in item.addons],
    )


@router.post("/menu/items", response_model=MenuItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(
    outlet_id: UUID,
    payload: MenuItemCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("menu.edit")),
):
    _get_category(db, outlet_id, payload.category_id)
    item = MenuItem(
        outlet_id=outlet_id,
        category_id=payload.category_id,
        name=payload.name,
        description=payload.description,
        base_price=payload.base_price,
        dietary_type=payload.dietary_type,
        is_available=payload.is_available,
        sort_order=payload.sort_order,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/menu/items/{item_id}", response_model=MenuItemResponse)
def update_item(
    outlet_id: UUID,
    item_id: UUID,
    payload: MenuItemUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("menu.edit")),
):
    item = _get_item(db, outlet_id, item_id)
    updates = payload.model_dump(exclude_unset=True)

    if "category_id" in updates:
        _get_category(db, outlet_id, updates["category_id"])
        item.category_id = updates["category_id"]
    if "name" in updates:
        item.name = updates["name"]
    if "description" in updates:
        item.description = updates["description"]
    if "base_price" in updates:
        item.base_price = updates["base_price"]
    if "dietary_type" in updates:
        item.dietary_type = updates["dietary_type"]
    if "is_available" in updates:
        item.is_available = updates["is_available"]
    if "sort_order" in updates:
        item.sort_order = updates["sort_order"]
    db.commit()
    db.refresh(item)
    return item


@router.delete("/menu/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    outlet_id: UUID,
    item_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("menu.edit")),
):
    item = _get_item(db, outlet_id, item_id)
    in_use = (
        db.query(OrderItem.id)
        .filter(OrderItem.menu_item_id == item_id)
        .first()
        is not None
    )
    _raise_if_referenced(
        in_use,
        "This item is on past orders, so it cannot be deleted. Mark it unavailable instead.",
    )
    _safe_delete(
        db,
        item,
        "This item is on past orders, so it cannot be deleted. Mark it unavailable instead.",
    )


@router.patch("/menu/items/{item_id}/availability", response_model=MenuItemResponse)
def update_item_availability(
    outlet_id: UUID,
    item_id: UUID,
    payload: MenuItemAvailabilityUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("menu.edit")),
):
    item = _get_item(db, outlet_id, item_id)
    item.is_available = payload.is_available
    db.commit()
    db.refresh(item)
    return item


@router.post(
    "/menu/items/{item_id}/images",
    response_model=MenuItemImageResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_item_image(
    outlet_id: UUID,
    item_id: UUID,
    payload: MenuItemImageCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("menu.edit")),
):
    _get_item(db, outlet_id, item_id)
    image = MenuItemImage(
        menu_item_id=item_id,
        image_url=payload.image_url,
        sort_order=payload.sort_order,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


@router.delete(
    "/menu/items/{item_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_item_image(
    outlet_id: UUID,
    item_id: UUID,
    image_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("menu.edit")),
):
    _get_item(db, outlet_id, item_id)
    image = _get_image(db, item_id, image_id)
    db.delete(image)
    db.commit()


@router.post(
    "/menu/items/{item_id}/variants",
    response_model=MenuItemVariantResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_item_variant(
    outlet_id: UUID,
    item_id: UUID,
    payload: MenuItemVariantCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("menu.edit")),
):
    item = _get_item(db, outlet_id, item_id)
    _ensure_variant_price_non_negative(item.base_price, payload.price_delta)
    variant = MenuItemVariant(
        menu_item_id=item_id,
        name=payload.name,
        price_delta=payload.price_delta,
        is_available=payload.is_available,
        sort_order=payload.sort_order,
    )
    db.add(variant)
    db.commit()
    db.refresh(variant)
    return variant


@router.patch(
    "/menu/items/{item_id}/variants/{variant_id}",
    response_model=MenuItemVariantResponse,
)
def update_item_variant(
    outlet_id: UUID,
    item_id: UUID,
    variant_id: UUID,
    payload: MenuItemVariantUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("menu.edit")),
):
    item = _get_item(db, outlet_id, item_id)
    variant = _get_variant(db, item_id, variant_id)
    if payload.name is not None:
        variant.name = payload.name
    if payload.price_delta is not None:
        _ensure_variant_price_non_negative(item.base_price, payload.price_delta)
        variant.price_delta = payload.price_delta
    if payload.is_available is not None:
        variant.is_available = payload.is_available
    if payload.sort_order is not None:
        variant.sort_order = payload.sort_order
    db.commit()
    db.refresh(variant)
    return variant


@router.delete(
    "/menu/items/{item_id}/variants/{variant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_item_variant(
    outlet_id: UUID,
    item_id: UUID,
    variant_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("menu.edit")),
):
    _get_item(db, outlet_id, item_id)
    variant = _get_variant(db, item_id, variant_id)
    in_use = (
        db.query(OrderItem.id)
        .filter(OrderItem.variant_id == variant_id)
        .first()
        is not None
    )
    _raise_if_referenced(
        in_use,
        "This size/variant is on past orders, so it cannot be deleted. Keep it and change the name or price instead.",
    )
    _safe_delete(
        db,
        variant,
        "This size/variant is on past orders, so it cannot be deleted. Keep it and change the name or price instead.",
    )


@router.post(
    "/menu/items/{item_id}/addons",
    response_model=MenuItemAddonResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_item_addon(
    outlet_id: UUID,
    item_id: UUID,
    payload: MenuItemAddonCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("menu.edit")),
):
    _get_item(db, outlet_id, item_id)
    addon = MenuItemAddon(
        menu_item_id=item_id,
        name=payload.name,
        price=payload.price,
        is_available=payload.is_available,
    )
    db.add(addon)
    db.commit()
    db.refresh(addon)
    return addon


@router.patch(
    "/menu/items/{item_id}/addons/{addon_id}",
    response_model=MenuItemAddonResponse,
)
def update_item_addon(
    outlet_id: UUID,
    item_id: UUID,
    addon_id: UUID,
    payload: MenuItemAddonUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("menu.edit")),
):
    _get_item(db, outlet_id, item_id)
    addon = _get_addon(db, item_id, addon_id)
    if payload.name is not None:
        addon.name = payload.name
    if payload.price is not None:
        addon.price = payload.price
    if payload.is_available is not None:
        addon.is_available = payload.is_available
    db.commit()
    db.refresh(addon)
    return addon


@router.delete(
    "/menu/items/{item_id}/addons/{addon_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_item_addon(
    outlet_id: UUID,
    item_id: UUID,
    addon_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("menu.edit")),
):
    _get_item(db, outlet_id, item_id)
    addon = _get_addon(db, item_id, addon_id)
    in_use = (
        db.query(OrderItemAddon.id)
        .filter(OrderItemAddon.addon_id == addon_id)
        .first()
        is not None
    )
    _raise_if_referenced(
        in_use,
        "This add-on is on past orders, so it cannot be deleted. Mark it unavailable instead.",
    )
    _safe_delete(
        db,
        addon,
        "This add-on is on past orders, so it cannot be deleted. Mark it unavailable instead.",
    )
