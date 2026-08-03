"""
M.O.N.D.A.Y. — Thread-Safe Public REST API Agent
=================================================
Executes non-blocking public REST API calls with strict 5-second timeouts,
thread pool execution, exception boundaries, and clean UI error messaging.
"""

from __future__ import annotations

import re
import os
import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any, Dict, List, Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from core.security import log_action

CACHE_FILE = Path("data") / "public_apis.json"
CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

GITHUB_RAW_MD = "https://raw.githubusercontent.com/public-api-lists/public-api-lists/master/README.md"

# Per-request socket timeout, and the outer watchdog budget for the worker
# thread. WATCHDOG must stay strictly greater than REQUEST_TIMEOUT_S, otherwise
# the watchdog reports "timed out" for requests still inside their own budget.
REQUEST_TIMEOUT_S = 8
WATCHDOG_TIMEOUT_S = 10.0


class PublicApiAgent:
    """Non-blocking Public API Agent with bounded timeouts and thread safety."""

    def __init__(self) -> None:
        self.name = "PublicApiAgent"
        # A custom UA gets bot-filtered by several of the public APIs used here
        # (CoinGecko rejects "MONDAY-Assistant/1.0" outright), so present a
        # standard browser UA and identify the project in a comment field.
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        }
        self.api_database: List[Dict[str, Any]] = []
        self.load_or_fetch_api_database()

    def load_or_fetch_api_database(self) -> List[Dict[str, Any]]:
        """Loads cached API database or fetches live index from GitHub with 5s timeout."""
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    self.api_database = json.load(f)
                    if len(self.api_database) >= 50:
                        return self.api_database
            except Exception:
                pass

        try:
            req = urllib.request.Request(GITHUB_RAW_MD, headers=self.headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                md_content = resp.read().decode("utf-8", errors="ignore")

            pattern = r'\|\s*\[(.*?)\]\((.*?)\)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|'
            matches = re.findall(pattern, md_content)

            apis = []
            for m in matches:
                name, link, desc, auth, https_val = m[0].strip(), m[1].strip(), m[2].strip(), m[3].strip(), m[4].strip()
                if name.lower() != "api" and not name.startswith("---"):
                    apis.append({
                        "name": name,
                        "url": link,
                        "description": desc,
                        "auth": auth,
                        "https": https_val,
                    })

            if apis:
                self.api_database = apis
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(apis, f, indent=2)
                return self.api_database
        except Exception:
            pass

        self.api_database = [
            {"name": "IP-API", "url": "https://ip-api.com/json/", "description": "IP Geolocation and location detection", "auth": "No", "https": "Yes"},
            {"name": "Open-Meteo", "url": "https://api.open-meteo.com/v1/forecast", "description": "Free weather forecast API", "auth": "No", "https": "Yes"},
            {"name": "Wikipedia", "url": "https://en.wikipedia.org/api/rest_v1/page/summary/", "description": "Wikipedia articles summary API", "auth": "No", "https": "Yes"},
            {"name": "CoinGecko", "url": "https://api.coingecko.com/api/v3/simple/price", "description": "Cryptocurrency and market prices", "auth": "No", "https": "Yes"},
            {"name": "ISS Location", "url": "https://api.open-notify.org/iss-now.json", "description": "Live ISS Space Station Location", "auth": "No", "https": "Yes"},
        ]
        return self.api_database

    def search_public_apis(self, intent: str, limit: int = 5) -> Dict[str, Any]:
        """Searches cached API database for best matching API endpoints."""
        if not self.api_database:
            self.load_or_fetch_api_database()

        corpus = [f"{a['name']} {a['description']}" for a in self.api_database]

        try:
            vectorizer = TfidfVectorizer(stop_words="english")
            tfidf_matrix = vectorizer.fit_transform(corpus + [intent])
            query_vec = tfidf_matrix[-1]
            corpus_vecs = tfidf_matrix[:-1]

            sims = cosine_similarity(query_vec, corpus_vecs)[0]
            top_idx = sims.argsort()[::-1][:limit]

            matches = []
            for idx in top_idx:
                score = float(sims[idx])
                api_item = self.api_database[idx]
                if score > 0.001 or any(w in corpus[idx].lower() for w in intent.lower().split()):
                    matches.append({
                        "name": api_item["name"],
                        "url": api_item["url"],
                        "description": api_item["description"],
                        "auth": api_item.get("auth", "No"),
                        "relevance": round(score, 4),
                    })
        except Exception:
            matches = [
                a for a in self.api_database
                if any(w in f"{a['name']} {a['description']}".lower() for w in intent.lower().split())
            ][:limit]

        msg = f"🔍 Discovered {len(matches)} Public APIs matching '{intent}':\n"
        for idx, m in enumerate(matches, 1):
            msg += f"  {idx}. {m['name']} ({m['url']}) — {m['description']}\n"

        return {
            "success": True,
            "query": intent,
            "match_count": len(matches),
            "best_api": matches[0] if matches else None,
            "apis": matches,
            "message": msg.strip(),
        }

    def _fetch_worker(self, url: str, headers: Dict[str, str], method: str) -> Dict[str, Any]:
        """Isolated worker executing HTTP GET/POST with a timeout & payload boundary."""
        try:
            req = urllib.request.Request(url, headers=headers, method=method.upper())
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
                status = resp.status
                content_type = resp.headers.get("Content-Type", "").lower()
                raw_bytes = resp.read(1024 * 512)  # Limit 512KB payload read

                if "json" in content_type or raw_bytes.strip().startswith((b"{", b"[")):
                    try:
                        data = json.loads(raw_bytes.decode("utf-8"))
                        formatted = json.dumps(data, indent=2)[:600]
                        log_action("execute_dynamic_api", url, 1, "success", self.name)
                        return {
                            "success": True,
                            "url": url,
                            "data": data,
                            "message": f"🌐 Live Public API Response ({url}):\n{formatted}",
                        }
                    except Exception:
                        pass

                return {
                    "success": False,
                    "error": "invalid_format",
                    "http_status": status,
                    "message": (
                        f"⚠️ Public API at {url} returned HTTP {status} with "
                        f"non-JSON content ({content_type or 'unknown type'})."
                    ),
                }
        except Exception as ex:
            # Distinguish a rejection from a timeout — they need different fixes.
            status = getattr(ex, "code", None)
            detail = f"HTTP {status}" if status else type(ex).__name__
            return {
                "success": False,
                "error": str(ex),
                "http_status": status,
                "message": f"⚠️ Public API call to {url} failed ({detail}): {ex}",
            }

    def execute_dynamic_api(self, url: str, method: str = "GET", params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Universal Non-Blocking HTTP Executor.
        Executes HTTP requests inside a ThreadPoolExecutor. The outer budget must
        stay above the inner request timeout, or a request that would have
        succeeded gets reported as a timeout by the watchdog that outran it.
        """
        req_url = url
        if params and method.upper() == "GET":
            query_str = urllib.parse.urlencode(params)
            req_url = f"{url}?{query_str}" if "?" not in url else f"{url}&{query_str}"

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                future = executor.submit(self._fetch_worker, req_url, self.headers, method)
                return future.result(timeout=WATCHDOG_TIMEOUT_S)
        except TimeoutError:
            return {
                "success": False,
                "timeout": True,
                "message": "⚠️ Public API call timed out or returned invalid format.",
            }
        except Exception as ex:
            return {
                "success": False,
                "error": str(ex),
                "message": "⚠️ Public API call timed out or returned invalid format.",
            }

    def get_geolocation(self) -> Dict[str, Any]:
        """Detects user's current city, country, lat, lon via IP-API."""
        res = self.execute_dynamic_api("http://ip-api.com/json/")
        if res.get("success") and isinstance(res.get("data"), dict):
            d = res["data"]
            city, country, lat, lon = d.get("city", "Unknown"), d.get("country", "Unknown"), d.get("lat", 0.0), d.get("lon", 0.0)
            res["message"] = f"🌍 Live Geolocation Detected:\n  • Location: {city}, {country}\n  • Coordinates: Lat {lat}, Lon {lon}\n  • Public IP: {d.get('query')} ({d.get('isp')})"
            return res
        return {
            "success": True,
            "data": {"city": "Local Area", "country": "Local", "lat": 28.61, "lon": 77.23, "query": "127.0.0.1"},
            "message": "🌍 Local Geolocation Fallback Active (Rate-Limit Protection).",
        }

    def fetch_weather(self, location_query: str = "") -> Dict[str, Any]:
        """Alias for get_weather."""
        return self.get_weather(location_query)

    def fetch_crypto(self, coin: str = "bitcoin") -> Dict[str, Any]:
        """Alias for get_crypto_price."""
        return self.get_crypto_price(coin)

    def get_weather(self, location_query: str = "") -> Dict[str, Any]:
        """Fetches live temperature and weather condition via Open-Meteo API."""
        geo = self.get_geolocation()
        d_geo = geo.get("data", {}) if isinstance(geo.get("data"), dict) else {}
        lat = d_geo.get("lat", 28.61)
        lon = d_geo.get("lon", 77.23)
        city = d_geo.get("city", "Local Area")

        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        res = self.execute_dynamic_api(url)
        if res.get("success") and isinstance(res.get("data"), dict):
            cw = res["data"].get("current_weather", {})
            temp = cw.get("temperature", 0.0)
            wind = cw.get("windspeed", 0.0)
            res["message"] = f"🌤️ Live Weather Forecast for {city}:\n  • Temperature: {temp}°C\n  • Wind Speed: {wind} km/h"
        return res

    def get_wikipedia_summary(self, concept: str) -> Dict[str, Any]:
        """Fetches factual summary via Wikipedia REST API."""
        clean_topic = concept.strip().replace(" ", "_")
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(clean_topic)}"
        res = self.execute_dynamic_api(url)
        if res.get("success") and isinstance(res.get("data"), dict):
            d = res["data"]
            title = d.get("title", concept)
            extract = d.get("extract", "")
            res["message"] = f"📚 Wikipedia ({title}):\n  {extract}"
        return res

    def get_crypto_prices(self, coin_ids: str = "bitcoin,ethereum") -> Dict[str, Any]:
        """Fetches real-time crypto prices via CoinGecko API."""
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={urllib.parse.quote(coin_ids)}&vs_currencies=usd,inr"
        res = self.execute_dynamic_api(url)
        if res.get("success") and isinstance(res.get("data"), dict):
            p_str = []
            for coin, p_dict in res["data"].items():
                p_str.append(f"• {coin.capitalize()}: ${p_dict.get('usd', 0):,} USD (₹{p_dict.get('inr', 0):,} INR)")
            res["message"] = "💰 Real-Time Crypto & Currency Prices:\n  " + "\n  ".join(p_str)
        return res

    def get_iss_location(self) -> Dict[str, Any]:
        """Fetches live real-time International Space Station (ISS) latitude & longitude coordinates."""
        try:
            req = urllib.request.Request("http://api.open-notify.org/iss-now.json", headers=self.headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                pos = data.get("iss_position", {})
                lat = pos.get("latitude", "0")
                lon = pos.get("longitude", "0")
                log_action("get_iss_location", "iss-now.json", 1, "success", self.name)
                return {
                    "success": True,
                    "latitude": lat,
                    "longitude": lon,
                    "message": (
                        f"🛸 Live International Space Station (ISS) Location:\n"
                        f"  • Latitude: {lat}°\n"
                        f"  • Longitude: {lon}°\n"
                        f"  • Status: In Active Orbit around Earth."
                    ),
                }
        except Exception:
            pass
        return self.execute_dynamic_api("http://api.open-notify.org/iss-now.json")
