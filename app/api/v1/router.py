from fastapi import APIRouter

from app.api.v1 import analytics, auth, billing, customers, health, menu, offers, orders, outlet_settings, outlet_subscription, payment_settings, platform, qr_studio, tables
from app.api.v1.public.content_posts import router as public_content_posts_router
from app.api.v1.public.users import router as public_users_router
from app.api.v1.public.menu import router as public_menu_router
from app.api.v1.public.media import router as public_media_router
from app.api.v1.public.orders import router as public_orders_router
from app.api.v1.public.outlets import router as public_outlets_router

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(platform.router)
api_router.include_router(menu.router)
api_router.include_router(tables.router)
api_router.include_router(qr_studio.router)
api_router.include_router(offers.router)
api_router.include_router(orders.router)
api_router.include_router(analytics.router)
api_router.include_router(billing.router)
api_router.include_router(payment_settings.router)
api_router.include_router(customers.router)
api_router.include_router(outlet_settings.router)
api_router.include_router(outlet_subscription.router)
api_router.include_router(public_media_router, prefix="/public")
api_router.include_router(public_menu_router, prefix="/public")
api_router.include_router(public_orders_router, prefix="/public")
api_router.include_router(public_users_router, prefix="/public")
api_router.include_router(public_outlets_router, prefix="/public")
api_router.include_router(public_content_posts_router, prefix="/public")
