"""Key/value settings stored on top of EngineState (state.db)."""
from typing import Optional

from sqlalchemy.orm import Session

from engine.models import EngineState


def get_setting(session: Session, key: str) -> Optional[str]:
    row = session.get(EngineState, key)
    return row.value if row else None


def set_setting(session: Session, key: str, value: str) -> None:
    row = session.get(EngineState, key)
    if row:
        row.value = value
    else:
        session.add(EngineState(key=key, value=value))
