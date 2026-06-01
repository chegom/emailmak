"""Email validation for syntax, blocked address classes, and cached MX checks."""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy.orm import Session

from engine.models import MxCache

_SYNTAX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MX_TTL = timedelta(days=7)

SYSTEM_LOCALPARTS = {
    "no-reply",
    "noreply",
    "donotreply",
    "do-not-reply",
    "postmaster",
    "mailer-daemon",
    "abuse",
    "bounce",
    "bounces",
}

ROLE_LOCALPARTS = {
    "info",
    "sales",
    "contact",
    "recruit",
    "hr",
    "jobs",
    "support",
    "admin",
    "help",
    "marketing",
    "career",
    "careers",
}

DISPOSABLE_DOMAINS = {
    "mailinator.com",
    "10minutemail.com",
    "guerrillamail.com",
    "tempmail.com",
    "trashmail.com",
    "yopmail.com",
}


def default_mx_lookup(domain: str) -> bool:
    import dns.resolver

    try:
        answers = dns.resolver.resolve(domain, "MX")
        return len(answers) > 0
    except Exception:
        return False


@dataclass
class ValidationResult:
    valid: list = field(default_factory=list)
    dropped: list = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        total = len(self.valid) + len(self.dropped)
        return len(self.valid) / total if total else 0.0


class EmailStatus:
    PASS = "pass"
    ROLE = "role"


class EmailValidator:
    def __init__(self, session: Session, mx_lookup: Callable[[str], bool] = default_mx_lookup):
        self.session = session
        self.mx_lookup = mx_lookup

    def _mx_valid(self, domain: str) -> bool:
        row = self.session.get(MxCache, domain)
        if row and row.checked_at and (datetime.utcnow() - row.checked_at) < _MX_TTL:
            return row.mx_valid

        valid = self.mx_lookup(domain)
        checked_at = datetime.utcnow()
        if row:
            row.mx_valid = valid
            row.checked_at = checked_at
        else:
            self.session.add(MxCache(domain=domain, mx_valid=valid, checked_at=checked_at))
        self.session.commit()
        return valid

    def validate(self, companies: list) -> ValidationResult:
        result = ValidationResult()

        for company in companies:
            for raw_email in company.get("emails", []):
                email = (raw_email or "").strip().lower()
                if not _SYNTAX.match(email):
                    result.dropped.append({"email": email, "reason": "syntax"})
                    continue

                local, domain = email.split("@", 1)
                if local in SYSTEM_LOCALPARTS:
                    result.dropped.append({"email": email, "reason": "system"})
                    continue
                if domain in DISPOSABLE_DOMAINS:
                    result.dropped.append({"email": email, "reason": "disposable"})
                    continue
                if not self._mx_valid(domain):
                    result.dropped.append({"email": email, "reason": "no_mx"})
                    continue

                result.valid.append({
                    "company_name": company.get("company_name"),
                    "email": email,
                    "domain": domain,
                    "is_role": local in ROLE_LOCALPARTS,
                    "job_title": company.get("job_title"),
                    "source": company.get("source"),
                })

        return result
