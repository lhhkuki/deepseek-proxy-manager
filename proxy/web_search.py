"""Web search handler — intercepts web_search tool calls and executes locally.

Search providers: Bing (primary) → Sogou → 360 → DuckDuckGo (fallback)
"""

import re as _re
import json as _json
from urllib.request import Request, urlopen
from urllib.parse import quote


_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def _search_bing(query, max_results=5):
    """Search via Bing."""
    url = f"https://www.bing.com/search?q={quote(query)}"
    req = Request(url, headers={"User-Agent": _UA})
    resp = urlopen(req, timeout=10)
    html = resp.read().decode("utf-8", errors="replace")
    results = []
    blocks = _re.split(r'<li class="b_algo"', html)[1:max_results + 1]
    for block in blocks:
        text = _re.sub(r'<[^>]+>', ' ', block)
        text = _re.sub(r'&[a-z]+;', ' ', text)
        text = _re.sub(r'&#?\w+;', ' ', text)
        text = _re.sub(r'\s+', ' ', text).strip()
        if len(text) > 20:
            results.append(text[:300])
    return results


def _search_sogou(query, max_results=5):
    """Search via Sogou."""
    url = f"https://www.sogou.com/web?query={quote(query)}"
    req = Request(url, headers={"User-Agent": _UA})
    resp = urlopen(req, timeout=10)
    html = resp.read().decode("utf-8", errors="replace")
    results = []
    blocks = _re.split(r'class="vrwrap"', html)[1:max_results + 1]
    for block in blocks:
        text = _re.sub(r'<[^>]+>', ' ', block)
        text = _re.sub(r'&[a-z]+;', ' ', text)
        text = _re.sub(r'&#?\w+;', ' ', text)
        text = _re.sub(r'\s+', ' ', text).strip()
        if len(text) > 20:
            results.append(text[:300])
    return results


def _search_360(query, max_results=5):
    """Search via 360 Search."""
    url = f"https://www.so.com/s?q={quote(query)}"
    req = Request(url, headers={"User-Agent": _UA})
    resp = urlopen(req, timeout=10)
    html = resp.read().decode("utf-8", errors="replace")
    results = []
    blocks = _re.split(r'class="res-list"', html)[1:max_results + 1]
    for block in blocks:
        text = _re.sub(r'<[^>]+>', ' ', block)
        text = _re.sub(r'&[a-z]+;', ' ', text)
        text = _re.sub(r'&#?\w+;', ' ', text)
        text = _re.sub(r'\s+', ' ', text).strip()
        if len(text) > 20:
            results.append(text[:300])
    return results


def _search_ddg(query, max_results=5):
    """Search via DuckDuckGo (last resort)."""
    url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
    req = Request(url, headers={"User-Agent": _UA})
    resp = urlopen(req, timeout=10)
    html = resp.read().decode("utf-8", errors="replace")
    results = []
    parts = html.split('class="result__snippet"')
    for part in parts[1:max_results + 1]:
        snippet = part.split("</")[0].strip()
        snippet = snippet.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", '"')
        if snippet and len(snippet) > 10:
            results.append(snippet)
    return results


_PROVIDERS = [
    ("Bing", _search_bing),
    ("Sogou", _search_sogou),
    ("360", _search_360),
    ("DuckDuckGo", _search_ddg),
]


def search(query: str, max_results: int = 5) -> str:
    """Search via available providers, trying each until one succeeds."""
    if not query:
        return "No search query provided."

    for name, fn in _PROVIDERS:
        try:
            results = fn(query, max_results)
            if results:
                return "\n\n".join(f"{i + 1}. {r}" for i, r in enumerate(results))
        except Exception:
            continue

    return f"No results found for: {query}"
