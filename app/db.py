"""
DB 엔진·세션 관리.
SQLite WAL 모드 + busy_timeout 5초.
"""
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(url: str) -> None:
    if url.startswith("sqlite:///") and ":memory:" not in url:
        db_path = Path(url.replace("sqlite:///", "", 1))
        db_path.parent.mkdir(parents=True, exist_ok=True)


_settings = get_settings()
_ensure_sqlite_dir(_settings.database_url)

engine = create_engine(
    _settings.database_url,
    connect_args={"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _enable_sqlite_pragmas(dbapi_conn, _):
    if _settings.database_url.startswith("sqlite"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA busy_timeout=5000;")
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    """FastAPI Depends용 세션 generator."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """워커·스크립트용 컨텍스트 매니저."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
