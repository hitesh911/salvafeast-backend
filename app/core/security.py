from datetime import datetime, timedelta, timezone

import hashlib
import hmac

import bcrypt
from jose import jwt

from app.core.config import settings


def _hash_value(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def _verify_value(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(plain: str) -> str:
    return _hash_value(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _verify_value(plain, hashed)


def hash_otp(otp_code: str) -> str:
    return _hash_value(otp_code)


def verify_otp(otp_code: str, hashed: str) -> bool:
    return _verify_value(otp_code, hashed)


def generate_otp_code() -> str:
    import secrets

    return str(secrets.randbelow(900000) + 100000)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_EXPIRE_MINUTES
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def access_token_expires_in_seconds() -> int:
    return settings.JWT_ACCESS_EXPIRE_MINUTES * 60


def create_support_access_token(data: dict) -> tuple[str, datetime]:
    """Platform support JWT; access TTL matches standard access tokens."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_EXPIRE_MINUTES
    )
    to_encode["exp"] = expire
    token = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return token, expire


def create_user_token(user_id: str, outlet_id: str | None = None) -> str:
    payload: dict = {
        "sub": user_id,
        "user_type": "user",
    }
    if outlet_id is not None:
        payload["outlet_id"] = outlet_id
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_EXPIRE_MINUTES
    )
    payload["exp"] = expire
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def hash_refresh_token(plain: str) -> str:
    return hmac.new(
        settings.JWT_SECRET_KEY.encode(),
        plain.encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_refresh_token(plain: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_refresh_token(plain), hashed)


def create_consumer_token(customer_id: str) -> str:
    """Deprecated: use create_user_token."""
    return create_user_token(customer_id)


ORDER_TRACKING_EXPIRE_HOURS = 48


def create_order_tracking_token(order_id: str, outlet_slug: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ORDER_TRACKING_EXPIRE_HOURS)
    payload = {
        "sub": order_id,
        "outlet_slug": outlet_slug,
        "user_type": "order_guest",
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_order_tracking_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
