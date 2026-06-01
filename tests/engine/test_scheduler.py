from datetime import datetime

from engine.models import RunLock
from engine.scheduler import acquire_lock, clear_stale_locks, due_rows, release_lock
from engine.sheets import ScheduleRow


def row(row_number, when, status="예정"):
    return ScheduleRow(row_number, when, "물류", "3PL", "ai", status)


def test_due_rows_filters_by_time_and_status():
    now = datetime(2026, 6, 4, 10, 0)
    rows = [
        row(2, "2026-06-04 09:00", "예정"),
        row(3, "2026-06-05 09:00", "예정"),
        row(4, "2026-06-01 09:00", "✅완료"),
        row(5, "2026-06-04", "예정"),
    ]
    due = due_rows(rows, now)
    assert [item.row_number for item in due] == [2, 5]


def test_lock_acquire_and_release(session):
    assert acquire_lock(session, "물류|2026-06-04 09:00") is True
    assert acquire_lock(session, "물류|2026-06-04 09:00") is False
    release_lock(session, "물류|2026-06-04 09:00")
    assert acquire_lock(session, "물류|2026-06-04 09:00") is True


def test_clear_stale_locks(session):
    session.add(RunLock(row_key="old", locked_at=datetime(2020, 1, 1)))
    session.commit()
    clear_stale_locks(session, before=datetime(2026, 1, 1))
    assert session.get(RunLock, "old") is None
