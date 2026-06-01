"""Gemini keyword generation with injectable text generation for tests."""
from typing import Callable, Optional

MODEL = "gemini-2.5-flash"


def _split_keywords(text: str) -> list:
    keywords = []
    for chunk in (text or "").replace("\n", ",").split(","):
        keyword = chunk.strip().lstrip("-•").strip()
        if keyword:
            keywords.append(keyword)
    return keywords


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str = MODEL,
        generate: Optional[Callable[[str], str]] = None,
    ):
        self.api_key = api_key
        self.model = model
        self._generate = generate or self._default_generate

    def _default_generate(self, prompt: str) -> str:
        from google import genai

        client = genai.Client(api_key=self.api_key)
        response = client.models.generate_content(model=self.model, contents=prompt)
        return response.text or ""

    def generate_keywords(self, industry: str, avoid: list, n: int) -> list:
        avoid_text = ", ".join(avoid) if avoid else "(없음)"
        prompt = (
            f"한국 채용사이트(사람인/잡코리아/원티드)에서 '{industry}' 산업군 기업을 "
            f"찾기 위한 검색 키워드를 {n}개 제안해줘. 회사가 채용공고에 쓸 법한 단어로. "
            f"다음 키워드는 제외: {avoid_text}. 설명 없이 쉼표로 구분된 키워드만 출력."
        )
        avoid_set = {keyword.strip() for keyword in avoid}
        out = []
        seen = set()
        for keyword in _split_keywords(self._generate(prompt)):
            if keyword in avoid_set or keyword in seen:
                continue
            seen.add(keyword)
            out.append(keyword)
            if len(out) >= n:
                break
        return out
