#!/usr/bin/env python3
"""Read Bilibili's public video search endpoint without credentials."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = "https://api.bilibili.com/x/web-interface/search/all/v2"
USER_AGENT = "research-router/bilibili-public"


def clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def request_json(url: str, timeout: float) -> dict:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"network error for {url}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"endpoint did not return JSON: {url}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Bilibili endpoint returned a non-object JSON value")
    return data


def search(query: str, page: int, limit: int, timeout: float) -> list[dict[str, object]]:
    params = urlencode({"keyword": query, "page": page})
    data = request_json(f"{API_URL}?{params}", timeout)
    if data.get("code") not in (0, None):
        raise RuntimeError(str(data.get("message") or f"Bilibili API code {data.get('code')}"))
    payload = data.get("data") or {}
    raw_results = payload.get("result") if isinstance(payload, dict) else []
    if isinstance(raw_results, dict):
        rows = []
        for group in raw_results.values():
            if isinstance(group, list):
                rows.extend(group)
            elif isinstance(group, dict) and isinstance(group.get("data"), list):
                rows.extend(group["data"])
    elif isinstance(raw_results, list) and any(
        isinstance(item, dict) and isinstance(item.get("data"), list) for item in raw_results
    ):
        rows = []
        for group in raw_results:
            if isinstance(group, dict) and isinstance(group.get("data"), list):
                rows.extend(group["data"])
    else:
        rows = raw_results or []
    results = []
    for item in rows[:limit]:
        if not isinstance(item, dict):
            continue
        bvid = item.get("bvid")
        url = f"https://www.bilibili.com/video/{bvid}" if bvid else item.get("arcurl") or ""
        results.append(
            {
                "title": clean_text(item.get("title")),
                "url": url,
                "excerpt": clean_text(item.get("description")),
                "published_at": item.get("pubdate"),
                "source": "bilibili-public",
                "query": query,
                "match_reason": "Bilibili public video search API",
                "evidence_level": "discovery",
                "author": clean_text(item.get("author")),
                "duration": item.get("duration"),
                "play_count": item.get("play"),
            }
        )
    return results


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args(argv[1:])
    if args.page < 1 or not 1 <= args.limit <= 50 or args.timeout <= 0:
        parser.error("page must be positive, limit must be 1..50, timeout must be positive")
    try:
        results = search(args.query, args.page, args.limit, args.timeout)
    except RuntimeError as exc:
        print(json.dumps({"status": "unavailable", "provider": "bilibili-public", "results": [], "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"status": "ok" if results else "partial", "provider": "bilibili-public", "query": args.query, "results": results, "evidence_level": "discovery"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
