"""Web search and scraping service for answering questions beyond document knowledge."""

import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from psk_bot.logging import get_logger
from psk_bot.settings import AppSettings, settings

logger = get_logger(__name__)


class WebSearchService:
    """Search the web and scrape content for questions not covered by documents."""

    def __init__(self, *, config: AppSettings = settings) -> None:
        self._config = config
        self._enabled = config.web_search_enabled
        self._max_results = config.web_search_max_results
        self._timeout = config.web_search_timeout
        self._session = None

    def _get_session(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            })
        return self._session

    @property
    def enabled(self) -> bool:
        return self._enabled

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search the web using DuckDuckGo HTML (no API key needed) and scrape top results."""
        if not self._enabled:
            logger.debug("Web search is disabled")
            return []

        results = []
        try:
            results = self._duckduckgo_search(query)
        except Exception:
            logger.exception("DuckDuckGo search failed, trying fallback")

        if not results:
            try:
                results = self._scrape_fallback(query)
            except Exception:
                logger.exception("Fallback search also failed")

        return results[:self._max_results]

    def _duckduckgo_search(self, query: str) -> List[Dict[str, Any]]:
        """Search using DuckDuckGo HTML interface (no API key required)."""
        import requests
        from bs4 import BeautifulSoup

        session = self._get_session()
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

        start = time.perf_counter()
        response = session.get(url, timeout=self._timeout)
        response.raise_for_status()
        elapsed = time.perf_counter() - start
        logger.info("DuckDuckGo search completed in %.2fs", elapsed)

        soup = BeautifulSoup(response.text, "html.parser")
        results = []

        for result_div in soup.select(".result"):
            title_tag = result_div.select_one(".result__a")
            snippet_tag = result_div.select_one(".result__snippet")
            url_tag = result_div.select_one(".result__url")

            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
            link = ""
            if url_tag:
                link = url_tag.get("href", url_tag.get_text(strip=True))
                if not link.startswith("http"):
                    link = "https://" + link.strip()

            # Also try extracting from the title's href
            if not link or "duckduckgo" in link:
                href = title_tag.get("href", "")
                if href and "uddg=" in href:
                    import urllib.parse
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    link = parsed.get("uddg", [""])[0]

            if title and snippet:
                results.append({
                    "title": title,
                    "snippet": snippet,
                    "url": link,
                    "source": "web",
                })

            if len(results) >= self._max_results + 2:
                break

        logger.info("Found %d web results for '%s'", len(results), query)
        return results

    def _scrape_fallback(self, query: str) -> List[Dict[str, Any]]:
        """Fallback: use a simpler approach if DDG fails."""
        return []

    def scrape_url(self, url: str, max_chars: int = 3000) -> Optional[str]:
        """Scrape and extract main content from a URL."""
        try:
            from bs4 import BeautifulSoup

            session = self._get_session()
            response = session.get(url, timeout=self._timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Remove script, style, nav, footer elements
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
                tag.decompose()

            # Try to find main content
            main_content = (
                soup.find("main")
                or soup.find("article")
                or soup.find("div", {"class": re.compile(r"content|article|post|entry", re.I)})
                or soup.find("body")
            )

            if not main_content:
                return None

            text = main_content.get_text(separator="\n", strip=True)
            # Clean up excessive whitespace
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = re.sub(r" {2,}", " ", text)

            if len(text) > max_chars:
                # Truncate at sentence boundary
                truncated = text[:max_chars]
                last_period = truncated.rfind(".")
                if last_period > max_chars * 0.7:
                    text = truncated[: last_period + 1]
                else:
                    text = truncated + "..."

            return text.strip() if len(text.strip()) > 100 else None

        except Exception:
            logger.exception("Failed to scrape URL: %s", url)
            return None

    def search_and_summarize(self, query: str) -> str:
        """Search the web and return a formatted context string for the LLM."""
        results = self.search(query)
        if not results:
            return ""

        context_parts = []
        for i, result in enumerate(results, 1):
            part = f"[Web Source {i}]: {result['title']}\n{result['snippet']}"

            # Try to scrape additional content from the URL
            if result.get("url"):
                scraped = self.scrape_url(result["url"], max_chars=1500)
                if scraped:
                    part += f"\n\nDetailed content:\n{scraped}"

            context_parts.append(part)

        return "\n\n---\n\n".join(context_parts)
