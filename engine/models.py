"""ORM models for engine state.db."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from engine.db import Base


class EngineState(Base):
    __tablename__ = "engine_state"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


class PushedEmail(Base):
    __tablename__ = "pushed_emails"

    email: Mapped[str] = mapped_column(String, primary_key=True)
    domain: Mapped[str] = mapped_column(String, index=True)
    campaign_id: Mapped[str] = mapped_column(String)
    pushed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MxCache(Base):
    __tablename__ = "mx_cache"

    domain: Mapped[str] = mapped_column(String, primary_key=True)
    mx_valid: Mapped[bool] = mapped_column(Boolean)
    checked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RunLock(Base):
    __tablename__ = "run_lock"

    row_key: Mapped[str] = mapped_column(String, primary_key=True)
    locked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
