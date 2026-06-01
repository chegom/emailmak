"""Keyword resolution: manual values win; Gemini fills blanks."""


def _split_keywords(text: str) -> list:
    return [
        keyword.strip()
        for keyword in (text or "").replace("\n", ",").split(",")
        if keyword.strip()
    ]


class KeywordResolver:
    def __init__(self, gemini=None):
        self.gemini = gemini

    def resolve(self, industry: str, manual: str, avoid: list, n: int):
        manual_keywords = _split_keywords(manual)
        if manual_keywords:
            return manual_keywords, "manual"
        if self.gemini is None:
            return [], "ai"
        return self.gemini.generate_keywords(industry, avoid, n), "ai"
