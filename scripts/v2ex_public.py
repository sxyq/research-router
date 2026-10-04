#!/usr/bin/env python3
"""Read V2EX's public API for hot topics, nodes, topics, replies, or users."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://www.v2ex.com"
USER_AGENT = "research-router/v2ex-public"


def request_json(url: str, timeout: float) -> object:
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


def api_url(base_url: str, path: str, **params: object) -> str:
    query = urlencode({key: value for key, value in params.items() if value is not None})
    return f"{base_url.rstrip('/')}{path}{'?' + query if query else ''}"


def normalize_topic(item: dict, base_url: str) -> dict[str, object]:
    node = item.get("node") or {}
    topic_id = item.get("id")
    return {
        "id": topic_id,
        "title": item.get("title", ""),
        "url": item.get("url") or f"{base_url.rstrip('/')}/t/{topic_id}",
        "excerpt": str(item.get("content") or "")[:400],
        "replies": item.get("replies", 0),
        "node": node.get("name", ""),
        "node_title": node.get("title", ""),
        "created": item.get("created"),
        "evidence_level": "detail",
    }


def fetch(mode: str, base_url: str, limit: int, timeout: float, node_name: str | None = None, topic_id: int | None = None, username: str | None = None) -> dict[str, object]:
    if mode == "hot":
        data = request_json(api_url(base_url, "/api/topics/hot.json"), timeout)
        rows = [normalize_topic(item, base_url) for item in (data if isinstance(data, list) else [])[:limit] if isinstance(item, dict)]
        return {"mode": mode, "results": rows}
    if mode == "node":
        if not node_name:
            raise ValueError("--node-name is required for node mode")
        data = request_json(api_url(base_url, "/api/topics/show.json", node_name=node_name, page=1), timeout)
        rows = [normalize_topic(item, base_url) for item in (data if isinstance(data, list) else [])[:limit] if isinstance(item, dict)]
        return {"mode": mode, "node_name": node_name, "results": rows}
    if mode == "topic":
        if topic_id is None:
            raise ValueError("--topic-id is required for topic/replies mode")
        topics = request_json(api_url(base_url, "/api/topics/show.json", id=topic_id), timeout)
        topic = topics[0] if isinstance(topics, list) and topics else topics if isinstance(topics, dict) else {}
        return {"mode": mode, "topic": normalize_topic(topic, base_url) if isinstance(topic, dict) else {}}
    if mode == "replies":
        if topic_id is None:
            raise ValueError("--topic-id is required for topic/replies mode")
        data = request_json(api_url(base_url, "/api/replies/show.json", topic_id=topic_id, page=1), timeout)
        rows = []
        for item in (data if isinstance(data, list) else [])[:limit]:
            if isinstance(item, dict):
                member = item.get("member") or {}
                rows.append({"id": item.get("id"), "author": member.get("username", ""), "text": item.get("content", ""), "created": item.get("created"), "evidence_level": "detail"})
        return {"mode": mode, "topic_id": topic_id, "results": rows}
    if mode == "user":
        if not username:
            raise ValueError("--username is required for user mode")
        data = request_json(api_url(base_url, "/api/members/show.json", username=username), timeout)
        return {"mode": mode, "user": data if isinstance(data, dict) else {}}
    raise ValueError(f"unsupported mode: {mode}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("hot", "node", "topic", "replies", "user"))
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--node-name")
    parser.add_argument("--topic-id", type=int)
    parser.add_argument("--username")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args(argv[1:])
    if not 1 <= args.limit <= 100 or args.timeout <= 0:
        parser.error("limit must be 1..100 and timeout must be positive")
    try:
        payload = fetch(args.mode, args.base_url, args.limit, args.timeout, args.node_name, args.topic_id, args.username)
    except (RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "unavailable", "provider": "v2ex-public", "mode": args.mode, "results": [], "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    value = payload.get("results", payload.get("topic", payload.get("user")))
    print(json.dumps({"status": "ok" if value else "partial", "provider": "v2ex-public", "public_api_scope": "hot/node/topic/replies/user; no full-text search", **payload}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
