"""Safe database URL construction for SQLAlchemy / Alembic."""

from __future__ import annotations

from urllib.parse import quote_plus


def build_database_url(
    *,
    user: str,
    password: str,
    host: str,
    port: int,
    name: str,
    driver: str = "postgresql+psycopg2",
) -> str:
    """
    Build a SQLAlchemy URL with special characters escaped.

    Passwords like `foo@bar` become `foo%40bar` so `@` is not treated as
    the host separator. Callers must not run this string through ConfigParser
    with default interpolation (use interpolation=None) or `%` will break.
    """
    return (
        f"{driver}://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{quote_plus(name)}"
    )
