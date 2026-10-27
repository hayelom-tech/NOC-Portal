from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from server.config import database_url


class Base(DeclarativeBase):
    pass


engine = create_engine(
    database_url(),
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
