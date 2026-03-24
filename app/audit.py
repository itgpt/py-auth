from sqlalchemy.orm import Session

from app.models import OperationLog


def add_operation_log(
    db: Session,
    username: str,
    action: str,
    target_type: str,
    target_id: str | None = None,
    detail: dict | None = None,
) -> None:
    db.add(
        OperationLog(
            username=username,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
        )
    )
