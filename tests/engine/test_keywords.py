from engine.gemini import GeminiClient
from engine.keywords import KeywordResolver


def test_gemini_parses_and_filters_avoid():
    generator = lambda prompt: "3PL, 풀필먼트, WMS, 풀필먼트"
    client = GeminiClient(api_key="k", generate=generator)
    keywords = client.generate_keywords("물류", avoid=["WMS"], n=5)
    assert keywords == ["3PL", "풀필먼트"]


def test_gemini_respects_n():
    generator = lambda prompt: "a, b, c, d, e, f"
    client = GeminiClient(api_key="k", generate=generator)
    assert client.generate_keywords("x", avoid=[], n=3) == ["a", "b", "c"]


def test_resolver_uses_manual_keyword():
    resolver = KeywordResolver(gemini=None)
    keywords, source = resolver.resolve(industry="물류", manual="3PL, 풀필먼트", avoid=[], n=5)
    assert keywords == ["3PL", "풀필먼트"]
    assert source == "manual"


def test_resolver_falls_back_to_gemini():
    class FakeGemini:
        def generate_keywords(self, industry, avoid, n):
            return ["콜드체인"]

    resolver = KeywordResolver(gemini=FakeGemini())
    keywords, source = resolver.resolve(industry="물류", manual="", avoid=[], n=5)
    assert keywords == ["콜드체인"]
    assert source == "ai"
