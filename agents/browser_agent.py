"""
M.O.N.D.A.Y. — Browser & Web Research Agent
============================================
Executes real web research and page scraping:
  • Live web search (DuckDuckGo / HTTP scraping)
  • Fetch & clean webpage content (BeautifulSoup)
  • Topic research synthesizer
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from core.security import log_action

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}


class BrowserAgent:
    """Specialized worker for web search, scraping, and web research synthesis."""

    def __init__(self) -> None:
        self.name = "BrowserAgent"

    def web_search(self, query: str, num_results: int = 5) -> Dict[str, Any]:
        """
        Performs a live web search using DuckDuckGo and parses result titles,
        links, and snippets.

        Tries the `html.` endpoint first, then falls back to the `lite.` one.
        Under load DuckDuckGo answers the html endpoint with HTTP 202 and an
        anomaly-challenge page instead of results, so a parse that yields
        nothing is treated as a failed search, not an empty one.
        """
        encoded = quote_plus(query)
        endpoints = (
            ("https://html.duckduckgo.com/html/?q=" + encoded, self._parse_ddg_html),
            ("https://lite.duckduckgo.com/lite/?q=" + encoded, self._parse_ddg_lite),
        )

        last_error: Optional[str] = None

        for url, parser in endpoints:
            try:
                with httpx.Client(headers=HEADERS, timeout=8.0, follow_redirects=True) as client:
                    resp = client.get(url)
            except Exception as e:
                last_error = f"WEB_SEARCH_ERROR: {e}"
                continue

            if resp.status_code != 200:
                # 202 = DuckDuckGo rate-limit / anomaly challenge.
                last_error = f"WEB_SEARCH_HTTP_{resp.status_code}"
                continue

            results = parser(resp.text, num_results)
            if results:
                log_action("web_search", query, 1, "success", self.name,
                           {"results_count": len(results)})
                return {
                    "success": True,
                    "query": query,
                    "result_count": len(results),
                    "results": results,
                    "message": f"✓ Found {len(results)} web search results for '{query}'.",
                }

            last_error = "WEB_SEARCH_NO_RESULTS"

        log_action("web_search", query, 1, "failed", self.name, {"error": last_error})
        return {
            "success": False,
            "query": query,
            "result_count": 0,
            "results": [],
            "error": last_error or "WEB_SEARCH_NO_RESULTS",
            "message": (
                f"❌ Web search for '{query}' returned no results "
                f"({last_error}). DuckDuckGo may be rate-limiting this machine."
            ),
        }

    @staticmethod
    def _parse_ddg_html(html: str, num_results: int) -> List[Dict[str, str]]:
        """Parses the `html.duckduckgo.com` result layout."""
        soup = BeautifulSoup(html, "html.parser")
        results: List[Dict[str, str]] = []
        for a in soup.select(".result__body")[:num_results]:
            title_elem = a.select_one(".result__title")
            snippet_elem = a.select_one(".result__snippet")
            link_elem = a.select_one(".result__url")

            title = title_elem.get_text(strip=True) if title_elem else "No title"
            snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
            link = link_elem.get_text(strip=True) if link_elem else ""

            if title and snippet:
                results.append({"title": title, "snippet": snippet, "url": link})
        return results

    @staticmethod
    def _parse_ddg_lite(html: str, num_results: int) -> List[Dict[str, str]]:
        """Parses the `lite.duckduckgo.com` table layout (title row + snippet row)."""
        soup = BeautifulSoup(html, "html.parser")
        results: List[Dict[str, str]] = []
        for link in soup.select("a.result-link")[:num_results]:
            title = link.get_text(strip=True)
            url = link.get("href", "")

            snippet = ""
            row = link.find_parent("tr")
            snippet_row = row.find_next_sibling("tr") if row else None
            if snippet_row:
                snippet_cell = snippet_row.select_one(".result-snippet")
                if snippet_cell:
                    snippet = snippet_cell.get_text(strip=True)

            if title and snippet:
                results.append({"title": title, "snippet": snippet, "url": url})
        return results

    def fetch_webpage_content(self, url: str, max_chars: int = 3000) -> Dict[str, Any]:
        """
        Fetches a target webpage, strips boilerplate (scripts, styles, nav),
        and returns clean body text.
        """
        if not url.startswith("http"):
            url = "https://" + url

        try:
            with httpx.Client(headers=HEADERS, timeout=10.0, follow_redirects=True) as client:
                resp = client.get(url)
                if resp.status_code != 200:
                    return {"success": False, "error": f"HTTP status {resp.status_code}"}

                soup = BeautifulSoup(resp.text, "html.parser")

                # Remove non-content tags
                for tag in soup(["script", "style", "nav", "footer", "header", "aside", "svg"]):
                    tag.decompose()

                text = soup.get_text(separator=" ", strip=True)
                # Normalise whitespace
                text = re.sub(r'\s+', ' ', text)

                title = soup.title.string if soup.title else url

                log_action("read_webpage", url, 1, "success", self.name, {"char_count": len(text)})

                return {
                    "success": True,
                    "url": url,
                    "title": title,
                    "content": text[:max_chars],
                    "total_chars": len(text),
                    "message": f"✓ Fetched page '{title}' ({len(text)} chars).",
                }
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch {url}: {e}"}

    def extract_webpage_markdown(self, url: str) -> Dict[str, Any]:
        """Fetches target web page and converts HTML structure into clean Markdown."""
        page_res = self.fetch_webpage_content(url)
        if not page_res.get("success"):
            return page_res

        title = page_res.get("title", "Webpage")
        content = page_res.get("content", "")
        
        # Format into clean markdown report
        markdown = f"# {title}\n\n**Source URL**: {url}\n\n"
        paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
        markdown += "\n\n".join(paragraphs[:30])

        log_action("extract_webpage_markdown", url, 1, "success", self.name)
        return {
            "success": True,
            "url": url,
            "title": title,
            "markdown_content": markdown,
            "message": f"✓ Extracted Markdown representation for '{title}'.",
        }

    def research_topic(self, topic: str) -> Dict[str, Any]:
        """
        Performs web research on a topic by running search queries,
        fetching snippets, and synthesizing a research summary.
        """
        search_res = self.web_search(topic, num_results=5)
        results = search_res.get("results", [])

        if not results:
            return {"success": False, "error": f"No web information found for '{topic}'."}

        summary_points = []
        for idx, r in enumerate(results, 1):
            summary_points.append(f"{idx}. [{r['title']}]\n   {r['snippet']}\n   Source: {r['url']}")

        report = f"Research Summary on '{topic}':\n\n" + "\n\n".join(summary_points)

        log_action("research_topic", topic, 1, "success", self.name, {"sources": len(results)})

        return {
            "success": True,
            "topic": topic,
            "sources_consulted": len(results),
            "report": report,
            "message": f"✓ Synthesised research report on '{topic}' from {len(results)} sources.",
        }

    def deep_research_and_scrape(self, query: str, num_results: int = 3) -> Dict[str, Any]:
        """
        Deep Headless Web Research: Spins up DOM scraping across top N search results,
        extracts clean webpage text, and synthesizes multi-source research insights.
        """
        search_res = self.web_search(query, num_results=num_results)
        results = search_res.get("results", [])

        if not results:
            return {"success": False, "error": f"No search results found for '{query}'."}

        scraped_sources = []
        for r in results[:num_results]:
            url = r.get("url", "")
            if url:
                pg_res = self.fetch_webpage_content(url, max_chars=2000)
                if pg_res.get("success"):
                    scraped_sources.append({
                        "title": r.get("title", pg_res.get("title", "Web Result")),
                        "url": url,
                        "snippet": r.get("snippet", ""),
                        "content": pg_res.get("content", ""),
                    })

        sources_count = len(scraped_sources)
        if sources_count == 0:
            return self.research_topic(query)

        formatted_sources = []
        for i, s in enumerate(scraped_sources, 1):
            excerpt = s['content'][:400] + "..." if len(s['content']) > 400 else s['content']
            formatted_sources.append(f"### Source {i}: [{s['title']}]({s['url']})\n**Snippet**: {s['snippet']}\n**Extracted DOM Excerpt**: {excerpt}")

        synthesis = f"## Deep Research Report: '{query}'\n\nConsulted {sources_count} top web pages in deep headless browser mode:\n\n" + "\n\n".join(formatted_sources)

        log_action("deep_research_and_scrape", query, 1, "success", self.name, {"sources_scraped": sources_count})

        return {
            "success": True,
            "query": query,
            "sources_scraped": sources_count,
            "report": synthesis,
            "message": f"✓ Deep research completed for '{query}'. Scraped {sources_count} top web pages.",
        }

    def open_app_or_website(self, target_name: str) -> Dict[str, Any]:
        """
        Smart Launcher: Delegates FIRST to ComputerAgent to search local machine binaries,
        and falls back to opening a web URL ONLY if local application is not found.
        """
        import webbrowser
        target = target_name.strip().lower()

        # Direct explicit web URLs pass through directly
        if target.startswith("http://") or target.startswith("https://") or (("." in target) and (not target.endswith(".exe"))):
            url = target if target.startswith("http") else f"https://{target}"
            webbrowser.open(url)
            log_action("open_website", url, 1, "success", self.name)
            return {
                "success": True,
                "target": target_name,
                "url": url,
                "message": f"✓ Opened Web URL ({url}).",
            }

        # Check Local App First via ComputerAgent
        from agents.computer_agent import ComputerAgent
        comp = ComputerAgent()
        return comp.launch_application(target_name)
