#!/usr/bin/env python3
"""Read Xueqiu public quote, stock search, hot post, and hot stock endpoints."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
REFERER = "https://xueqiu.com/"
XUEQIU_HOME = "https://xueqiu.com"
XUEQIU_COOKIE_ENV = "XUEQIU_COOKIE"
COOKIE_JAR = http.cookiejar.CookieJar()
OPENER = build_opener(HTTPCookieProcessor(COOKIE_JAR))
SESSION_READY = False


def inject_cookie_string(cookie_str: str) -> None:
    """Inject an explicitly supplied cookie string into the Xueqiu jar."""
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        name, _, value = pair.partition("=")
        cookie = http.cookiejar.Cookie(
            version=0,
            name=name.strip(),
            value=value.strip(),
            port=None,
            port_specified=False,
            domain=".xueqiu.com",
            domain_specified=True,
            domain_initial_dot=True,
            path="/",
            path_specified=True,
            secure=True,
            expires=None,
            discard=True,
            comment=None,
            comment_url=None,
            rest={},
        )
        COOKIE_JAR.set_cookie(cookie)


def load_configured_cookie() -> bool:
    """Load only the explicitly supplied XUEQIU_COOKIE environment value."""
    cookie_str = os.environ.get(XUEQIU_COOKIE_ENV)
    if not cookie_str:
        return False
    inject_cookie_string(cookie_str)
    return True


def ensure_public_session(timeout: float) -> None:
    global SESSION_READY
    if SESSION_READY:
        return
    if load_configured_cookie():
        SESSION_READY = True
        return
    request = Request(XUEQIU_HOME, headers={"User-Agent": USER_AGENT})
    with OPENER.open(request, timeout=timeout):
        pass
    SESSION_READY = True


def request_json(url: str, timeout: float) -> object:
    ensure_public_session(timeout)
    request = Request(url, headers={"User-Agent": USER_AGENT, "Referer": REFERER})
    try:
        with OPENER.open(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"network error for {url}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"endpoint did not return JSON: {url}") from exc


def clean_text(value: object) -> str:
    text = re.sub(r"<[^>]+>", "", str(value or ""))
    for entity, char in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">")):
        text = text.replace(entity, char)
    return text.strip()


def fetch(mode: str, query: str | None, symbol: str | None, limit: int, timeout: float) -> dict[str, object]:
    if mode == "search-stock":
        if not query:
            raise ValueError("--query is required for search-stock")
        data = request_json(f"https://xueqiu.com/stock/search.json?{urlencode({'code': query, 'size': limit})}", timeout)
        rows = []
        stocks = (data.get("stocks") or []) if isinstance(data, dict) else []
        for item in stocks[:limit]:
            if isinstance(item, dict):
                rows.append({"symbol": item.get("code", ""), "name": item.get("name", ""), "exchange": item.get("exchange", ""), "evidence_level": "discovery"})
        return {"mode": mode, "results": rows}
    if mode == "quote":
        if not symbol:
            raise ValueError("--symbol is required for quote")
        data = request_json(f"https://stock.xueqiu.com/v5/stock/quote.json?{urlencode({'symbol': symbol, 'extend': 'detail'})}", timeout)
        quote_data = ((data.get("data") or {}).get("quote") or {}) if isinstance(data, dict) else {}
        if not isinstance(quote_data, dict):
            quote_data = {}
        return {
            "mode": mode,
            "quote": {
                "symbol": quote_data.get("symbol", symbol),
                "name": quote_data.get("name", ""),
                "current": quote_data.get("current"),
                "percent": quote_data.get("percent"),
                "chg": quote_data.get("chg"),
                "high": quote_data.get("high"),
                "low": quote_data.get("low"),
                "open": quote_data.get("open"),
                "last_close": quote_data.get("last_close"),
                "volume": quote_data.get("volume"),
                "amount": quote_data.get("amount"),
                "market_capital": quote_data.get("market_capital"),
                "turnover_rate": quote_data.get("turnover_rate"),
                "pe_ttm": quote_data.get("pe_ttm"),
                "pe_forecast": quote_data.get("pe_forecast"),
                "pb": quote_data.get("pb"),
                "eps": quote_data.get("eps"),
                "timestamp": quote_data.get("timestamp"),
            },
        }
    if mode == "hot-posts":
        if limit < 0:
            raise ValueError("limit must be non-negative")
        limit = min(limit, 50)
        if limit == 0:
            return {"mode": mode, "results": []}
        data = request_json("https://xueqiu.com/v4/statuses/public_timeline_by_category.json?since_id=-1&max_id=-1&" + urlencode({"count": limit, "category": -1}), timeout)
        rows = []
        items = (data.get("list") or []) if isinstance(data, dict) else []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue
            raw = item.get("data")
            try:
                post = json.loads(raw) if isinstance(raw, str) else {}
            except (json.JSONDecodeError, TypeError):
                post = {}
            if not isinstance(post, dict):
                post = {}
            user = post.get("user") or {}
            target = post.get("target") or ""
            if not isinstance(user, dict):
                user = {}
            rows.append({"id": post.get("id", 0), "title": post.get("title") or "", "text": clean_text(post.get("text") or post.get("description"))[:200], "author": user.get("screen_name", ""), "likes": post.get("like_count", 0), "url": f"https://xueqiu.com{target}" if target else "", "evidence_level": "discovery"})
        return {"mode": mode, "results": rows}
    if mode == "hot-stocks":
        data = request_json(f"https://stock.xueqiu.com/v5/stock/hot_stock/list.json?{urlencode({'size': limit, 'type': 10})}", timeout)
        rows = []
        for index, item in enumerate((((data.get("data") or {}).get("items") or []) if isinstance(data, dict) else [])[:limit], 1):
            if isinstance(item, dict):
                rows.append({"symbol": item.get("code") or item.get("symbol", ""), "name": item.get("name", ""), "current": item.get("current"), "percent": item.get("percent"), "rank": index, "evidence_level": "discovery"})
        return {"mode": mode, "results": rows}
    raise ValueError(f"unsupported mode: {mode}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("search-stock", "quote", "hot-posts", "hot-stocks"))
    parser.add_argument("--query")
    parser.add_argument("--symbol")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args(argv[1:])
    if not 1 <= args.limit <= 50 or args.timeout <= 0:
        parser.error("limit must be 1..50 and timeout must be positive")
    try:
        payload = fetch(args.mode, args.query, args.symbol, args.limit, args.timeout)
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "unavailable", "provider": "xueqiu-public", "mode": args.mode, "results": [], "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    value = payload.get("results", payload.get("quote"))
    print(json.dumps({"status": "ok" if value else "partial", "provider": "xueqiu-public", "access_scope": "public endpoint; login may be required by current anti-abuse policy", **payload}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
