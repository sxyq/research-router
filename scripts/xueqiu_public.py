#!/usr/bin/env python3
"""Read Xueqiu public quote, stock search, hot post, and hot stock endpoints."""

from __future__ import annotations

import argparse
import http.cookiejar
import html
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


USER_AGENT = "research-router/xueqiu-public"
REFERER = "https://xueqiu.com/"
COOKIE_JAR = http.cookiejar.CookieJar()
OPENER = build_opener(HTTPCookieProcessor(COOKIE_JAR))
SESSION_READY = False


def ensure_public_session(timeout: float) -> None:
    global SESSION_READY
    if SESSION_READY:
        return
    request = Request(REFERER, headers={"User-Agent": USER_AGENT})
    try:
        with OPENER.open(request, timeout=timeout):
            pass
    except Exception:
        # The API request below will report the concrete endpoint failure.
        pass
    SESSION_READY = True


def request_json(url: str, timeout: float) -> object:
    ensure_public_session(timeout)
    request = Request(url, headers={"User-Agent": USER_AGENT, "Referer": REFERER, "Accept": "application/json"})
    try:
        with OPENER.open(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"network error for {url}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"endpoint did not return JSON: {url}") from exc


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(str(value or "")))).strip()


def fetch(mode: str, query: str | None, symbol: str | None, limit: int, timeout: float) -> dict[str, object]:
    if mode == "search-stock":
        if not query:
            raise ValueError("--query is required for search-stock")
        data = request_json(f"https://xueqiu.com/stock/search.json?{urlencode({'code': query, 'size': limit})}", timeout)
        rows = []
        for item in (data.get("stocks") if isinstance(data, dict) else [])[:limit]:
            if isinstance(item, dict):
                rows.append({"symbol": item.get("code", ""), "name": item.get("name", ""), "exchange": item.get("exchange", ""), "evidence_level": "discovery"})
        return {"mode": mode, "results": rows}
    if mode == "quote":
        if not symbol:
            raise ValueError("--symbol is required for quote")
        data = request_json(f"https://stock.xueqiu.com/v5/stock/quote.json?{urlencode({'symbol': symbol, 'extend': 'detail'})}", timeout)
        quote_data = ((data.get("data") or {}).get("quote") or {}) if isinstance(data, dict) else {}
        return {"mode": mode, "quote": quote_data}
    if mode == "hot-posts":
        data = request_json("https://xueqiu.com/v4/statuses/public_timeline_by_category.json?since_id=-1&max_id=-1&" + urlencode({"count": limit, "category": -1}), timeout)
        rows = []
        for item in ((data.get("list") or []) if isinstance(data, dict) else [])[:limit]:
            if not isinstance(item, dict):
                continue
            raw = item.get("data")
            post = json.loads(raw) if isinstance(raw, str) else {}
            user = post.get("user") or {}
            target = post.get("target") or ""
            rows.append({"id": post.get("id"), "title": clean_text(post.get("title")), "text": clean_text(post.get("text") or post.get("description"))[:400], "author": user.get("screen_name", ""), "likes": post.get("like_count", 0), "url": f"https://xueqiu.com{target}" if target else "", "evidence_level": "discovery"})
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
