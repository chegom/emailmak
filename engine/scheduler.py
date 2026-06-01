"""Scheduler helpers: due-row filtering and run-lock management."""
from datetime import datetime

from engine.models import RunLock


def _parse_when(when: str) -> datetime:
    value = (when or "").strip()
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M")
    except ValueError:
        return datetime.strptime(value.split(" ")[0], "%Y-%m-%d").replace(hour=9, minute=0)


def due_rows(rows: list, now: datetime) -> list:
    due = []
    for row in rows:
        if row.status != "예정":
            continue
        try:
            when = _parse_when(row.when)
        except ValueError:
            continue
        if when <= now:
            due.append(row)
    return due


def lock_key(row) -> str:
    return f"{row.industry}|{row.when}"


def acquire_lock(session, key: str) -> bool:
    if session.get(RunLock, key):
        return False
    session.add(RunLock(row_key=key, locked_at=datetime.utcnow()))
    session.commit()
    return True


def release_lock(session, key: str):
    row = session.get(RunLock, key)
    if row:
        session.delete(row)
        session.commit()


def clear_stale_locks(session, before: datetime):
    for lock in session.query(RunLock).filter(RunLock.locked_at < before).all():
        session.delete(lock)
    session.commit()
