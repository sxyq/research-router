#!/usr/bin/env python3
"""Search a public Discourse forum and optionally read one topic."""

from __future__ import annotations

import argparse
import json
import re
import sys
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


USER_AGENT = "research-router/discourse-search"


def base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise argparse.ArgumentTypeError("base URL must include http:// or https://")
    return value.rstrip("/")


def request_json(url: str, timeout: float) -> dict:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"network error for {url}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"endpoint did not return JSON: {url}") from exc


def clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", unescape(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def search(args: argparse.Namespace) -> dict:
    params = {"q": args.query, "page": args.page}
    if args.category:
        params["category"] = args.category
    if args.tag:
        params["tags"] = args.tag
    data = request_json(f"{args.base_url}/search.json?{urlencode(params)}", args.timeout)
    titles = {topic.get("id"): topic.get("title") for topic in data.get("topics", [])}
    posts = []
    for post in data.get("posts", [])[: args.limit]:
        posts.append({
            "topic_id": post.get("topic_id"),
            "post_id": post.get("id"),
            "post_number": post.get("post_number"),
            "author": post.get("username") or post.get("name"),
            "created_at": post.get("created_at"),
            "title": post.get("topic_title") or titles.get(post.get("topic_id")),
            "excerpt": clean_text(post.get("blurb", "")),
            "url": f"{args.base_url}/t/{post.get('topic_id')}" if post.get("topic_id") else None,
        })
    return {"mode": "search", "base_url": args.base_url, "query": args.query, "results": posts}


def topic(args: argparse.Namespace) -> dict:
    data = request_json(f"{args.base_url}/t/{quote(str(args.topic_id))}.json", args.timeout)
    stream = data.get("post_stream", {}).get("posts", [])
    posts = []
    for post in stream[: args.limit]:
        posts.append({
            "post_id": post.get("id"),
            "post_number": post.get("post_number"),
            "author": post.get("username") or post.get("name"),
            "created_at": post.get("created_at"),
            "text": clean_text(post.get("cooked", "")),
        })
    return {
        "mode": "topic",
        "base_url": args.base_url,
        "topic_id": args.topic_id,
        "title": data.get("title"),
        "url": f"{args.base_url}/t/{args.topic_id}",
        "results": posts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, type=base_url)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--query")
    group.add_argument("--topic-id", type=int)
    parser.add_argument("--category")
    parser.add_argument("--tag")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()
    if args.page < 1 or not 1 <= args.limit <= 100 or args.timeout <= 0:
        parser.error("page must be positive, limit must be 1..100, timeout must be positive")
    try:
        result = search(args) if args.query is not None else topic(args)
    except RuntimeError as exc:
        print(json.dumps({"status": "unavailable", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"status": "verified", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
