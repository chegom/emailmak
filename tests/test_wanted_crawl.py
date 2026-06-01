import pytest

from crawlers.wanted import WantedCrawler


@pytest.mark.asyncio
async def test_crawl_with_emails_uses_api_id_and_sorts(monkeypatch):
    crawler = WantedCrawler()

    async def fake_search(keyword, start_page=1, end_page=5):
        return [
            {
                "company_name": "A",
                "company_url": "u/1",
                "api_id": "1",
                "job_url": None,
                "job_title": "A 채용",
                "homepage": None,
                "emails": [],
            },
            {
                "company_name": "B",
                "company_url": "u/2",
                "api_id": "2",
                "job_url": None,
                "job_title": "B 채용",
                "homepage": None,
                "emails": [],
            },
        ]

    async def fake_detail(api_id):
        return {"homepage": f"http://site-{api_id}.com"}

    async def fake_extract(url):
        return ["b@site-2.com"] if "site-2" in url else []

    monkeypatch.setattr(crawler, "search", fake_search)
    monkeypatch.setattr(crawler, "get_company_detail", fake_detail)
    monkeypatch.setattr(crawler.email_extractor, "extract_from_url", fake_extract)

    result = await crawler.crawl_with_emails("물류", 1, 1)

    assert result[0]["company_name"] == "B"
    assert result[0]["emails"] == ["b@site-2.com"]
    assert result[1]["emails"] == []
