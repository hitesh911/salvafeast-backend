from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.db_url import build_database_url


class Settings(BaseSettings):
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str
    DB_NAME: str = "salva"


    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60
    JWT_ACCESS_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS: int = 90
    OTP_EXPIRE_MINUTES: int = 10
    OTP_MAX_ATTEMPTS: int = 5

    PLATFORM_ADMIN_EMAIL: str = "admin@example.com"
    PLATFORM_ADMIN_PASSWORD: str = "changeme"
    PLATFORM_ADMIN_NAME: str = "Platform Admin"

    GCS_BUCKET_NAME: str = ""
    # Optional local override only. Cloud Run uses ADC (runtime SA) — leave empty.
    GCS_SERVICE_ACCOUNT_JSON_PATH: str = ""
    # Optional; ADC usually provides project. Set if Client() needs an explicit project.
    GCS_PROJECT_ID: str = ""
    # Optional SA email for V4 signed URLs when using ADC (Cloud Run). If empty,
    # uses credentials.service_account_email from the metadata server.
    GCS_SIGNING_SERVICE_ACCOUNT: str = ""
    GCS_SIGNED_URL_EXPIRE_MINUTES: int = 15

    # Local disk media when SALVA_ENV=local (no GCS)
    LOCAL_MEDIA_DIR: str = "local_media"
    LOCAL_MEDIA_BASE_URL: str = "http://localhost:8000/local-media"

    CONSUMER_WEB_BASE_URL: str = "https://order.salva.app"
    CONSUMER_JWT_EXPIRE_HOURS: int = 24

    # Comma-separated browser origins allowed to call the API (admin web, etc.)
    CORS_ALLOWED_ORIGINS: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3001,http://127.0.0.1:3001"
    )

    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_CONTACT_EMAIL: str = "support@salva.app"

    # Controls whether we should actually send OTPs or just print/log them.
    # local = never call external providers (save money); dev/production = use SMS_PROVIDER.
    SALVA_ENV: str = "local"

    SMS_PROVIDER: str = "console"
    FAST2SMS_AUTH_KEY: str = ""
    FAST2SMS_PHONE_NUMBER_ID: str = ""
    FAST2SMS_MESSAGE_ID: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def push_notifications_enabled(self) -> bool:
        return bool(self.VAPID_PRIVATE_KEY.strip() and self.VAPID_PUBLIC_KEY.strip())

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return build_database_url(
            user=self.DB_USER,
            password=self.DB_PASSWORD,
            host=self.DB_HOST,
            port=self.DB_PORT,
            name=self.DB_NAME,
        )


settings = Settings()
