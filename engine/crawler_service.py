"""Crawler adapter that calls the existing site crawlers."""
from crawlers import SaraminCrawler
from crawlers.jobkorea import JobKoreaCrawler
from crawlers.wanted import WantedCrawler

CRAWLERS = {
    "saramin": SaraminCrawler,
    "jobkorea": JobKoreaCrawler,
    "wanted": WantedCrawler,
}


def _parse_pages(spec: str):
    value = (spec or "1-5").strip()
    if "-" in value:
        start, end = value.split("-", 1)
        return int(start), int(end)
    page = int(value)
    return page, page


class CrawlerService:
    async def crawl(self, sites: list, keywords: list, pages: str) -> list:
        start_page, end_page = _parse_pages(pages)
        companies = []

        for site in sites:
            crawler_class = CRAWLERS.get(site)
            if not crawler_class:
                continue
            async with crawler_class() as crawler:
                for keyword in keywords:
                    found = await crawler.crawl_with_emails(keyword, start_page, end_page)
                    for company in found:
                        company["source"] = site
                    companies.extend(found)

        return companies
