"""Deduplication against emails accepted by Smartlead pushes."""
from sqlalchemy.orm import Session

from engine.models import PushedEmail


def _norm(email: str) -> str:
    return (email or "").strip().lower()


class DedupStore:
    def __init__(self, session: Session):
        self.session = session

    def _already(self, email: str) -> bool:
        return self.session.get(PushedEmail, _norm(email)) is not None

    def filter_new(self, records: list) -> list:
        return [record for record in records if not self._already(record["email"])]

    def mark_pushed(self, records: list, campaign_id: str) -> None:
        for record in records:
            email = _norm(record["email"])
            if self.session.get(PushedEmail, email):
                continue
            self.session.add(PushedEmail(
                email=email,
                domain=record.get("domain") or email.split("@", 1)[-1],
                campaign_id=campaign_id,
            ))
        self.session.commit()

    def backfill(self, records: list) -> None:
        for record in records:
            email = _norm(record["email"])
            if self.session.get(PushedEmail, email):
                continue
            self.session.add(PushedEmail(
                email=email,
                domain=record.get("domain") or email.split("@", 1)[-1],
                campaign_id=record.get("campaign_id", ""),
            ))
        self.session.commit()
