"""Smartlead API client for batched lead pushes and campaign analytics."""
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

BASE_URL = "https://server.smartlead.ai/api/v1"
BATCH_SIZE = 100
PUSH_SETTINGS = {
    "ignore_global_block_list": True,
    "ignore_unsubscribe_list": True,
    "ignore_duplicate_leads_in_other_campaign": True,
}


@dataclass
class PushResult:
    accepted: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    note: str = ""


def _to_lead(record: dict) -> dict:
    return {
        "email": record["email"],
        "company_name": record.get("company_name") or "",
        "custom_fields": {
            "job_title": record.get("job_title") or "",
            "source": record.get("source") or "",
        },
    }


class SmartleadClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = BASE_URL,
        client: Optional[httpx.Client] = None,
        sleep=time.sleep,
        max_retries: int = 5,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.client = client or httpx.Client(timeout=30.0)
        self.sleep = sleep
        self.max_retries = max_retries

    def _params(self) -> dict:
        return {"api_key": self.api_key}

    def push_leads(self, campaign_id: str, records: list) -> PushResult:
        result = PushResult()
        url = f"{self.base_url}/campaigns/{campaign_id}/leads"

        for index in range(0, len(records), BATCH_SIZE):
            batch = records[index:index + BATCH_SIZE]
            body = {
                "lead_list": [_to_lead(record) for record in batch],
                "settings": PUSH_SETTINGS,
            }
            try:
                response = self._post_with_retry(url, body)
            except httpx.HTTPError as exc:
                result.failed.extend(batch)
                result.note = f"http_error: {exc}"
                continue

            if response.status_code // 100 == 2:
                result.accepted.extend(batch)
            else:
                result.failed.extend(batch)
                result.note = f"{response.status_code}: {response.text[:200]}"

        return result

    def _post_with_retry(self, url: str, body: dict) -> httpx.Response:
        response = None
        for attempt in range(self.max_retries):
            response = self.client.post(url, params=self._params(), json=body)
            if response.status_code in (429, 500, 502, 503) and attempt < self.max_retries - 1:
                self.sleep(min(60, 2 ** attempt))
                continue
            return response
        return response  # type: ignore[return-value]

    def get_campaign_stats(self, campaign_id: str) -> dict:
        url = f"{self.base_url}/campaigns/{campaign_id}/analytics"
        response = self.client.get(url, params=self._params())
        response.raise_for_status()
        data = response.json()
        sent = int(data.get("sent_count") or data.get("sent") or 0)
        bounced = int(data.get("bounce_count") or data.get("bounced") or data.get("bounces") or 0)
        return {"sent": sent, "bounced": bounced}
