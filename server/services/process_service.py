"""Business rules for NOC process records."""
from sqlalchemy.orm import Session

from server.models import NOCProcess
from server.repositories.process_repository import ProcessRepository


class ProcessService:
    """Coordinates process persistence and validation boundaries."""

    def __init__(self, db: Session):
        self.repository = ProcessRepository(db)

    def list_active(self, *, category: str | None = None, limit: int = 200, offset: int = 0):
        return self.repository.list_active(category=category, limit=limit, offset=offset)

    def create(self, process: NOCProcess) -> NOCProcess:
        self.repository.add(process)
        self.repository.save()
        self.repository.refresh(process)
        return process
