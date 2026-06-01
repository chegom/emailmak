import httpx
import respx

from engine.smartlead import SmartleadClient

BASE = "https://server.smartlead.ai/api/v1"


def _records(*emails):
    return [
        {
            "email": email,
            "company_name": "C",
            "job_title": "t",
            "source": "saramin",
            "domain": email.split("@")[1],
            "is_role": False,
        }
        for email in emails
    ]


@respx.mock
def test_push_leads_batches_and_marks_accepted():
    route = respx.post(f"{BASE}/campaigns/42/leads").mock(
        return_value=httpx.Response(200, json={"upload_count": 2})
    )
    client = SmartleadClient(api_key="k", client=httpx.Client())
    result = client.push_leads("42", _records("a@x.com", "b@y.com"))

    assert route.called
    sent_request = route.calls[0].request
    assert "api_key=k" in str(sent_request.url)
    assert {record["email"] for record in result.accepted} == {"a@x.com", "b@y.com"}
    assert result.failed == []


@respx.mock
def test_push_leads_splits_over_100():
    respx.post(f"{BASE}/campaigns/42/leads").mock(return_value=httpx.Response(200, json={}))
    client = SmartleadClient(api_key="k", client=httpx.Client())
    records = _records(*[f"u{i}@x.com" for i in range(250)])
    client.push_leads("42", records)
    assert respx.calls.call_count == 3


@respx.mock
def test_push_leads_4xx_marks_failed():
    respx.post(f"{BASE}/campaigns/42/leads").mock(
        return_value=httpx.Response(400, json={"message": "bad"})
    )
    client = SmartleadClient(api_key="k", client=httpx.Client())
    result = client.push_leads("42", _records("a@x.com"))
    assert result.accepted == []
    assert [record["email"] for record in result.failed] == ["a@x.com"]


@respx.mock
def test_get_campaign_stats():
    respx.get(f"{BASE}/campaigns/42/analytics").mock(
        return_value=httpx.Response(200, json={"sent_count": "100", "bounce_count": "7"})
    )
    client = SmartleadClient(api_key="k", client=httpx.Client())
    stats = client.get_campaign_stats("42")
    assert stats == {"sent": 100, "bounced": 7}
