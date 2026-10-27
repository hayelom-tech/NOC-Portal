"""Repository for database-backed NOC process records."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from server.models import NOCProcess


class ProcessRepository:
    """Queries and persists NOC process entities."""

    def __init__(self, db: Session):
        self.db = db

    def list_active(self, *, category: str | None = None, limit: int = 200, offset: int = 0):
        query = select(NOCProcess).where(NOCProcess.is_active.is_(True)).order_by(
            NOCProcess.category, NOCProcess.title
        )
        if category:
            query = query.where(NOCProcess.category == category)
        return self.db.scalars(query.offset(offset).limit(limit)).all()

    def get(self, process_id: int) -> NOCProcess | None:
        return self.db.get(NOCProcess, process_id)

    def add(self, process: NOCProcess) -> NOCProcess:
        self.db.add(process)
        self.db.flush()
        return process

    def save(self) -> None:
        self.db.commit()

    def refresh(self, process: NOCProcess) -> None:
        self.db.refresh(process)
