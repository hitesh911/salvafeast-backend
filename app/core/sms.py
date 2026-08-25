import logging
from abc import ABC, abstractmethod

import httpx

from app.core.config import Settings
from app.core.phone import INDIAN_PHONE_PATTERN

logger = logging.getLogger(__name__)

FAST2SMS_WHATSAPP_BASE_URL = "https://www.fast2sms.com/dev/whatsapp"
FAST2SMS_REQUEST_TIMEOUT_SECONDS = 10.0


class SmsProvider(ABC):
    @abstractmethod
    def send_otp(self, phone: str, otp_code: str) -> bool:
        pass


class ConsoleSmsProvider(SmsProvider):
    def send_otp(self, phone: str, otp_code: str) -> bool:
        print(f"[OTP] phone={phone} code={otp_code}", flush=True)
        logger.info("OTP %s for %s", otp_code, phone)
        return True


class Fast2SmsWhatsAppProvider(SmsProvider):
    def __init__(
        self,
        auth_key: str,
        phone_number_id: str,
        message_id: str,
    ) -> None:
        self._auth_key = auth_key
        self._phone_number_id = phone_number_id
        self._message_id = message_id

    def send_otp(self, phone: str, otp_code: str) -> bool:
        if not INDIAN_PHONE_PATTERN.fullmatch(phone):
            logger.error(
                "WhatsApp OTP send failed: invalid phone format for %s",
                _mask_phone(phone),
            )
            return False

        params = {
            "message_id": self._message_id,
            "phone_number_id": self._phone_number_id,
            "numbers": f"91{phone}",
            "variables_values": otp_code,
        }
        headers = {
            "Authorization": self._auth_key,
            "accept": "application/json",
        }

        try:
            response = httpx.get(
                FAST2SMS_WHATSAPP_BASE_URL,
                params=params,
                headers=headers,
                timeout=FAST2SMS_REQUEST_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            logger.error(
                "WhatsApp OTP send failed for %s: network error (%s)",
                _mask_phone(phone),
                exc,
            )
            return False

        if response.status_code != 200:
            logger.error(
                "WhatsApp OTP send failed for %s: HTTP %s body=%s",
                _mask_phone(phone),
                response.status_code,
                _truncate(response.text),
            )
            return False

        try:
            body = response.json()
        except ValueError:
            logger.error(
                "WhatsApp OTP send failed for %s: invalid JSON body=%s",
                _mask_phone(phone),
                _truncate(response.text),
            )
            return False

        if isinstance(body, dict):
            if body.get("return") is False:
                logger.error(
                    "WhatsApp OTP send failed for %s: response=%s",
                    _mask_phone(phone),
                    _truncate(str(body)),
                )
                return False
            status_value = str(body.get("status", "")).lower()
            if status_value in {"error", "failed", "failure"}:
                logger.error(
                    "WhatsApp OTP send failed for %s: response=%s",
                    _mask_phone(phone),
                    _truncate(str(body)),
                )
                return False
        elif "error" in response.text.lower():
            logger.error(
                "WhatsApp OTP send failed for %s: response=%s",
                _mask_phone(phone),
                _truncate(response.text),
            )
            return False

        logger.info(
            "WhatsApp OTP sent for %s using message_id=%s",
            _mask_phone(phone),
            self._message_id,
        )
        return True


_sms_provider: SmsProvider | None = None


def init_sms_provider(settings: Settings) -> None:
    global _sms_provider
    env_mode = settings.SALVA_ENV.strip().lower()
    if env_mode == "local":
        _sms_provider = ConsoleSmsProvider()
        print("[SMS] SALVA_ENV=local — OTP will print here, not sent via WhatsApp", flush=True)
        logger.info("SMS provider initialized: console (local mode)")
        return
    if env_mode not in {"dev", "production"}:
        raise ValueError(
            f"Unknown SALVA_ENV: {settings.SALVA_ENV!r} (expected local|dev|production)"
        )
    provider = settings.SMS_PROVIDER.strip().lower()
    if provider == "whatsapp":
        missing = [
            name
            for name, value in (
                ("FAST2SMS_AUTH_KEY", settings.FAST2SMS_AUTH_KEY),
                ("FAST2SMS_PHONE_NUMBER_ID", settings.FAST2SMS_PHONE_NUMBER_ID),
                ("FAST2SMS_MESSAGE_ID", settings.FAST2SMS_MESSAGE_ID),
            )
            if not value.strip()
        ]
        if missing:
            raise ValueError(
                f"SMS_PROVIDER=whatsapp requires: {', '.join(missing)}"
            )
        _sms_provider = Fast2SmsWhatsAppProvider(
            auth_key=settings.FAST2SMS_AUTH_KEY.strip(),
            phone_number_id=settings.FAST2SMS_PHONE_NUMBER_ID.strip(),
            message_id=settings.FAST2SMS_MESSAGE_ID.strip(),
        )
        logger.info("SMS provider initialized: whatsapp")
    elif provider == "console":
        _sms_provider = ConsoleSmsProvider()
        logger.info("SMS provider initialized: console")
    else:
        raise ValueError(f"Unknown SMS_PROVIDER: {settings.SMS_PROVIDER!r}")


def get_sms_provider() -> SmsProvider:
    if _sms_provider is None:
        raise RuntimeError("SMS provider not initialized")
    return _sms_provider


def _mask_phone(phone: str) -> str:
    digits = phone.strip()
    if len(digits) <= 4:
        return "****"
    return f"{'*' * (len(digits) - 4)}{digits[-4:]}"


def _truncate(text: str, limit: int = 500) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}..."
