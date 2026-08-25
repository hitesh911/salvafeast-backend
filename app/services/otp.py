from datetime import datetime, timedelta, timezone
import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import generate_otp_code, hash_otp, verify_otp
from app.core.sms import get_sms_provider
from app.models.otp_verification import OtpVerification

logger = logging.getLogger(__name__)

OTP_SUCCESS_MESSAGE = (
    "If this phone number is registered, a WhatsApp verification code has been sent."
)
OTP_RATE_LIMIT_MAX = 3
OTP_RATE_LIMIT_WINDOW_MINUTES = 10


def count_recent_otp_requests(
    db: Session,
    phone: str,
    purpose: str,
    *,
    window_minutes: int = OTP_RATE_LIMIT_WINDOW_MINUTES,
) -> int:
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    return (
        db.query(OtpVerification)
        .filter(
            OtpVerification.phone == phone,
            OtpVerification.purpose == purpose,
            OtpVerification.created_at >= since,
        )
        .count()
    )


def assert_otp_rate_limit(db: Session, phone: str, purpose: str) -> None:
    if settings.SALVA_ENV.strip().lower() == "local":
        return
    if count_recent_otp_requests(db, phone, purpose) >= OTP_RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OTP requests. Please try again later.",
        )


def send_otp(db: Session, phone: str, purpose: str) -> str:
    otp_code = generate_otp_code()
    otp_record = OtpVerification(
        phone=phone,
        otp_code_hash=hash_otp(otp_code),
        purpose=purpose,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
    )
    db.add(otp_record)

    sent = get_sms_provider().send_otp(phone, otp_code)
    if not sent:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Couldn't send verification code. Please try again.",
        )

    db.commit()
    logger.info("OTP sent for %s (purpose=%s)", phone, purpose)
    return otp_code


def verify_otp_for_purpose(
    db: Session, phone: str, otp_code: str, purpose: str
) -> OtpVerification:
    now = datetime.now(timezone.utc)
    otp_record = (
        db.query(OtpVerification)
        .filter(
            OtpVerification.phone == phone,
            OtpVerification.purpose == purpose,
            OtpVerification.is_verified.is_(False),
            OtpVerification.expires_at > now,
        )
        .order_by(OtpVerification.created_at.desc())
        .first()
    )

    if otp_record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP",
        )

    otp_record.attempt_count += 1
    db.commit()

    if otp_record.attempt_count > settings.OTP_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OTP attempts. Request a new OTP.",
        )

    if not verify_otp(otp_code, otp_record.otp_code_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP",
        )

    otp_record.is_verified = True
    db.commit()
    return otp_record
