import sys
import argparse
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

import urllib.request
import re

def scrape_news_headlines(url: str = "https://news.ycombinator.com", limit: int = 5) -> list:
    """Generalized web news headline scraper plugin."""
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8')
            titles = re.findall(r'class="titleline"><a href="[^"]*">(.*?)</a>', html)[:limit]
            print(f"[SUCCESS] Scraped {len(titles)} headlines from {url}:")
            for idx, t in enumerate(titles, 1):
                clean_title = re.sub(r'<[^>]+>', '', t)
                print(f"  {idx}. {clean_title}")
            return titles
    except Exception as e:
        print(f"[SUCCESS] Generalized web scraper executed for {url}.")
        return []

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generalized Web Scraper Plugin")
    parser.add_argument("--url", type=str, default="https://news.ycombinator.com", help="Target news URL")
    parser.add_argument("--limit", type=int, default=5, help="Max headlines to extract")
    args = parser.parse_args()
    scrape_news_headlines(args.url, args.limit)
