from app.models.outlet import Outlet
from app.schemas.outlet_settings import OutletProfileSettingsResponse
from app.schemas.public import PublicOutletInfo, PublicOutletSummary


def cuisine_tag_list(outlet: Outlet) -> list[str]:
    tags = outlet.cuisine_tags if isinstance(outlet.cuisine_tags, list) else []
    return [str(tag) for tag in tags]


def build_outlet_profile_response(outlet: Outlet) -> OutletProfileSettingsResponse:
    return OutletProfileSettingsResponse(
        name=outlet.name,
        phone=outlet.phone,
        address=outlet.address,
        address_line1=outlet.address_line1,
        address_line2=outlet.address_line2,
        landmark=outlet.landmark,
        area=outlet.area,
        city=outlet.city,
        state=outlet.state,
        pincode=outlet.pincode,
        latitude=outlet.latitude,
        longitude=outlet.longitude,
        email=outlet.email,
        whatsapp_phone=outlet.whatsapp_phone,
        description=outlet.description,
        cuisine_tags=cuisine_tag_list(outlet),
        opening_hours=outlet.opening_hours
        if isinstance(outlet.opening_hours, dict)
        else None,
        fssai_number=outlet.fssai_number,
        cost_for_two=outlet.cost_for_two,
        is_pure_veg=bool(outlet.is_pure_veg),
        outlet_type=outlet.outlet_type,
        logo_url=outlet.logo_url,
        cover_image_url=outlet.cover_image_url,
        slug=outlet.slug,
    )


def build_public_outlet_info(outlet: Outlet) -> PublicOutletInfo:
    return PublicOutletInfo(
        id=outlet.id,
        slug=outlet.slug,
        name=outlet.name,
        logo_url=outlet.logo_url,
        cover_image_url=outlet.cover_image_url,
        address=outlet.address,
        address_line1=outlet.address_line1,
        address_line2=outlet.address_line2,
        landmark=outlet.landmark,
        area=outlet.area,
        city=outlet.city,
        state=outlet.state,
        pincode=outlet.pincode,
        latitude=outlet.latitude,
        longitude=outlet.longitude,
        phone=outlet.phone,
        description=outlet.description,
        cuisine_tags=cuisine_tag_list(outlet),
        opening_hours=outlet.opening_hours
        if isinstance(outlet.opening_hours, dict)
        else None,
        cost_for_two=outlet.cost_for_two,
        is_pure_veg=bool(outlet.is_pure_veg),
        outlet_type=outlet.outlet_type,
        verification_status=outlet.verification_status,
    )


def build_public_outlet_summary(outlet: Outlet) -> PublicOutletSummary:
    return PublicOutletSummary(
        id=outlet.id,
        slug=outlet.slug,
        name=outlet.name,
        logo_url=outlet.logo_url,
        cover_image_url=outlet.cover_image_url,
        address=outlet.address,
        city=outlet.city,
        area=outlet.area,
        cuisine_tags=cuisine_tag_list(outlet),
        cost_for_two=outlet.cost_for_two,
        is_pure_veg=bool(outlet.is_pure_veg),
        verification_status=outlet.verification_status,
    )
