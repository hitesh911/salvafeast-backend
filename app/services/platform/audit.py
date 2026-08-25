from uuid import UUID

from sqlalchemy.orm import Session

from app.models.platform_audit_log import PlatformAuditLog


def log_platform_action(
    db: Session,
    *,
    actor_id: UUID,
    action: str,
    resource_type: str,
    resource_id: UUID | None = None,
    metadata: dict | None = None,
) -> PlatformAuditLog:
    entry = PlatformAuditLog(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_json=metadata,
    )
    db.add(entry)
    db.flush()
    return entry
