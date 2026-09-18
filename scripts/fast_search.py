#!/usr/bin/env python3
"""Run compact, public, no-key research searches.

The script intentionally returns discovery records instead of raw pages. Use a
platform-specific reader or a selected source URL for the next evidence step.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


USER_AGENT = "research-router/fast-search 1.0"
DEFAULT_TIMEOUT = 15.0
MAX_EXCERPT = 420


class SearchError(RuntimeError):
    """A public endpoint could not produce a usable result."""


def clean_text(value: object, limit: int = MAX_EXCERPT) -> str:
    text = re.sub(r"<[^>]+>", " ", unescape(str(value or "")))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].rstrip() + ("..." if len(text) > limit else "")


def unix_iso(value: object) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def request_bytes(
    url: str,
    params: dict[str, object] | None,
    timeout: float,
    accept: str = "application/json",
) -> bytes:
    if params:
        url = f"{url}?{urlencode(params, doseq=True)}"
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except HTTPError as exc:
        retry_after = exc.headers.get("Retry-After")
        suffix = f"; retry-after={retry_after}" if retry_after else ""
        raise SearchError(f"HTTP {exc.code} from {url}{suffix}") from exc
    except URLError as exc:
        raise SearchError(f"network error for {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise SearchError(f"timeout for {url}") from exc


def request_json(
    url: str,
    params: dict[str, object] | None,
    timeout: float,
) -> dict | list:
    payload = request_bytes(url, params, timeout)
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SearchError(f"endpoint did not return JSON: {url}") from exc


def record(
    title: object,
    url: object,
    excerpt: object,
    published_at: object,
    source: str,
    query: str,
    match_reason: str | None = None,
) -> dict[str, object]:
    return {
        "title": clean_text(title, 240),
        "url": str(url or ""),
        "published_at": published_at,
        "excerpt": clean_text(excerpt),
        "source": source,
        "match_reason": match_reason or f"public search match for: {query}",
        "evidence_level": "discovery",
    }


def search_github(args: argparse.Namespace) -> list[dict[str, object]]:
    data = request_json(
        "https://api.github.com/search/repositories",
        {"q": args.query, "per_page": args.limit},
        args.timeout,
    )
    return [
        record(
            item.get("full_name") or item.get("name"),
            item.get("html_url"),
            item.get("description"),
            item.get("updated_at"),
            "github",
            args.query,
            f"repository search; stars={item.get('stargazers_count', 0)}",
        )
        for item in data.get("items", [])[: args.limit]
    ]


def search_stackoverflow(args: argparse.Namespace) -> list[dict[str, object]]:
    data = request_json(
        "https://api.stackexchange.com/2.3/search/advanced",
        {
            "site": "stackoverflow",
            "q": args.query,
            "order": "desc",
            "sort": "relevance",
            "pagesize": args.limit,
        },
        args.timeout,
    )
    return [
        record(
            item.get("title"),
            item.get("link"),
            f"tags={', '.join(item.get('tags', []))}; "
            f"answers={item.get('answer_count', 0)}; "
            f"answered={item.get('is_answered', False)}",
            unix_iso(item.get("last_activity_date")),
            "stackoverflow",
            args.query,
            "Stack Exchange relevance search",
        )
        for item in data.get("items", [])[: args.limit]
    ]


def search_hacker_news(args: argparse.Namespace) -> list[dict[str, object]]:
    data = request_json(
        "https://hn.algolia.com/api/v1/search",
        {"query": args.query, "hitsPerPage": args.limit},
        args.timeout,
    )
    results = []
    for item in data.get("hits", [])[: args.limit]:
        object_id = item.get("objectID")
        url = item.get("url") or (
            f"https://news.ycombinator.com/item?id={object_id}" if object_id else ""
        )
        results.append(
            record(
                item.get("title") or item.get("story_title"),
                url,
                item.get("story_text") or item.get("comment_text"),
                item.get("created_at"),
                "hacker-news",
                args.query,
                "HN Algolia search",
            )
        )
    return results


def search_devto(args: argparse.Namespace) -> list[dict[str, object]]:
    tag = args.query.strip().lower().replace(" ", "-")
    data = request_json(
        "https://dev.to/api/articles",
        {"tag": tag, "per_page": args.limit},
        args.timeout,
    )
    return [
        record(
            item.get("title"),
            item.get("url"),
            item.get("description"),
            item.get("published_at") or item.get("created_at"),
            "dev-to",
            args.query,
            f"Forem tag listing: {tag}",
        )
        for item in data[: args.limit]
    ]


def search_wikipedia(args: argparse.Namespace) -> list[dict[str, object]]:
    language = args.language or "en"
    api_url = f"https://{language}.wikipedia.org/w/api.php"
    data = request_json(
        api_url,
        {
            "action": "query",
            "list": "search",
            "srsearch": args.query,
            "srlimit": args.limit,
            "format": "json",
        },
        args.timeout,
    )
    results = []
    for item in data.get("query", {}).get("search", [])[: args.limit]:
        title = item.get("title")
        results.append(
            record(
                title,
                f"https://{language}.wikipedia.org/wiki/{quote(str(title or '').replace(' ', '_'))}",
                item.get("snippet"),
                None,
                "wikipedia",
                args.query,
                "MediaWiki search",
            )
        )
    return results


def search_openalex(args: argparse.Namespace) -> list[dict[str, object]]:
    data = request_json(
        "https://api.openalex.org/works",
        {"search": args.query, "per-page": args.limit},
        args.timeout,
    )
    results = []
    for item in data.get("results", [])[: args.limit]:
        location = item.get("primary_location") or {}
        source = location.get("source") or {}
        results.append(
            record(
                item.get("title"),
                location.get("landing_page_url") or item.get("doi") or item.get("id"),
                f"authors={', '.join((author.get('author') or {}).get('display_name', '') for author in item.get('authorships', [])[:3])}; "
                f"venue={source.get('display_name', '')}; cited_by={item.get('cited_by_count', 0)}",
                item.get("publication_date"),
                "openalex",
                args.query,
                "OpenAlex works search",
            )
        )
    return results


def search_crossref(args: argparse.Namespace) -> list[dict[str, object]]:
    data = request_json(
        "https://api.crossref.org/works",
        {"query": args.query, "rows": args.limit},
        args.timeout,
    )
    results = []
    for item in data.get("message", {}).get("items", [])[: args.limit]:
        title = (item.get("title") or [""])[0]
        dates = item.get("published-print") or item.get("published-online") or {}
        parts = dates.get("date-parts", [[]])[0]
        published_at = "-".join(str(part) for part in parts) if parts else None
        url = item.get("URL") or (
            f"https://doi.org/{item.get('DOI')}" if item.get("DOI") else ""
        )
        results.append(
            record(
                title,
                url,
                f"authors={', '.join(author.get('family', '') for author in item.get('author', [])[:3])}; "
                f"type={item.get('type', '')}; DOI={item.get('DOI', '')}",
                published_at,
                "crossref",
                args.query,
                "Crossref metadata search",
            )
        )
    return results


def search_arxiv(args: argparse.Namespace) -> list[dict[str, object]]:
    payload = request_bytes(
        "https://export.arxiv.org/api/query",
        {"search_query": f"all:{args.query}", "max_results": args.limit},
        args.timeout,
        accept="application/atom+xml",
    )
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise SearchError("arXiv endpoint did not return valid Atom XML") from exc
    results = []
    for entry in root.findall("{http://www.w3.org/2005/Atom}entry")[: args.limit]:
        def child(name: str) -> str:
            node = entry.find(f"{{http://www.w3.org/2005/Atom}}{name}")
            return node.text.strip() if node is not None and node.text else ""

        results.append(
            record(
                child("title"),
                child("id"),
                child("summary"),
                child("published") or None,
                "arxiv",
                args.query,
                "arXiv Atom search",
            )
        )
    return results


def search_discourse(args: argparse.Namespace) -> list[dict[str, object]]:
    if not args.base_url:
        raise SearchError("--base-url is required for the discourse provider")
    base = args.base_url.rstrip("/")
    params: dict[str, object] = {"q": args.query, "page": args.page}
    if args.category:
        params["category"] = args.category
    if args.tag:
        params["tags"] = args.tag
    data = request_json(f"{base}/search.json", params, args.timeout)
    titles = {topic.get("id"): topic.get("title") for topic in data.get("topics", [])}
    results = []
    for item in data.get("posts", [])[: args.limit]:
        topic_id = item.get("topic_id")
        results.append(
            record(
                item.get("topic_title") or titles.get(topic_id),
                f"{base}/t/{topic_id}" if topic_id else "",
                item.get("blurb"),
                item.get("created_at"),
                "discourse",
                args.query,
                "Discourse public search.json",
            )
        )
    return results


def xml_value(element: ET.Element, names: set[str]) -> str:
    for child in list(element):
        if local_name(child.tag) in names:
            return (child.text or "").strip()
    return ""


def search_rss(args: argparse.Namespace) -> list[dict[str, object]]:
    if not args.feed_url:
        raise SearchError("--feed-url is required for the rss provider")
    payload = request_bytes(args.feed_url, None, args.timeout, accept="application/rss+xml, application/atom+xml, text/xml")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise SearchError("RSS endpoint did not return valid XML") from exc
    results = []
    for item in root.iter():
        if local_name(item.tag) not in {"item", "entry"}:
            continue
        link = xml_value(item, {"link"})
        link_node = next((child for child in list(item) if local_name(child.tag) == "link"), None)
        if link_node is not None:
            link = link_node.attrib.get("href") or link
        results.append(
            record(
                xml_value(item, {"title"}),
                link,
                xml_value(item, {"description", "summary", "content"}),
                xml_value(item, {"pubDate", "published", "updated"}) or None,
                "rss",
                args.query,
                "RSS/Atom feed entry",
            )
        )
        if len(results) >= args.limit:
            break
    return results


def search_ddgs(args: argparse.Namespace) -> list[dict[str, object]]:
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise SearchError("ddgs is not installed; install the optional no-key package") from exc
    results = []
    for item in DDGS().text(args.query, max_results=args.limit):
        results.append(
            record(
                item.get("title"),
                item.get("href") or item.get("url"),
                item.get("body") or item.get("snippet"),
                item.get("date"),
                "ddgs",
                args.query,
                "multi-engine web discovery",
            )
        )
    return results


SEARCHERS = {
    "github": search_github,
    "stackoverflow": search_stackoverflow,
    "hacker-news": search_hacker_news,
    "dev-to": search_devto,
    "wikipedia": search_wikipedia,
    "openalex": search_openalex,
    "crossref": search_crossref,
    "arxiv": search_arxiv,
    "discourse": search_discourse,
    "rss": search_rss,
    "ddgs": search_ddgs,
}


LIMITS = {
    "github": ["Unauthenticated GitHub Search API requests are rate limited."],
    "stackoverflow": ["Respect Stack Exchange quota, backoff, and API policies."],
    "openalex": ["Public access may return 429; retry later and identify the client when possible."],
    "arxiv": ["Use a polite request interval; the endpoint is for discovery metadata."],
    "crossref": ["Metadata is discovery evidence; read the source or DOI page for claims."],
    "ddgs": ["Underlying search engines may vary in availability and ranking."],
    "rss": ["A feed covers only the publisher's exposed entries, not its full archive."],
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=sorted(SEARCHERS))
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--base-url")
    parser.add_argument("--feed-url")
    parser.add_argument("--category")
    parser.add_argument("--tag")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--language", default="en")
    args = parser.parse_args()
    if not 1 <= args.limit <= 50:
        parser.error("--limit must be between 1 and 50")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.page < 1:
        parser.error("--page must be positive")
    try:
        results = SEARCHERS[args.provider](args)
    except SearchError as exc:
        print(
            json.dumps(
                {
                    "status": "unavailable",
                    "provider": args.provider,
                    "query": args.query,
                    "results": [],
                    "evidence_level": "none",
                    "limits": [str(exc)],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "status": "ok" if results else "partial",
                "provider": args.provider,
                "query": args.query,
                "results": results,
                "evidence_level": "discovery",
                "next_action": "read_selected",
                "limits": LIMITS.get(args.provider, []),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
