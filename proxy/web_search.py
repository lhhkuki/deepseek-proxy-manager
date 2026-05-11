"""Web search handler — intercepts web_search tool calls and executes locally."""

import json as _json
from urllib.request import Request, urlopen
from urllib.parse import quote


def search(query: str, max_results: int = 5) -> str:
    """Search via DuckDuckGo HTML and return formatted results."""
    if not query:
        return "No search query provided."

    try:
        url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp = urlopen(req, timeout=10)
        html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"Search failed: {e}"

    # Parse result snippets
    results = []
    parts = html.split('class="result__snippet"')
    for part in parts[1:max_results + 1]:
        snippet = part.split("</")[0].strip()
        snippet = snippet.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", '"')
        if snippet and len(snippet) > 10:
            results.append(snippet)

    if not results:
        return f"No results found for: {query}"

    return "\n\n".join(f"{i + 1}. {r}" for i, r in enumerate(results))
