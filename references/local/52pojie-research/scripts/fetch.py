#!/usr/bin/env python3
"""Fetch public 52pojie forum pages and emit structured UTF-8 JSON."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree


BASE_URL = "https://www.52pojie.cn/"
USER_AGENT = "research-router/52pojie-research 1.0"
THREAD_PATH = re.compile(r"^thread-(?P<tid>\d+)-(?P<page>\d+)-1\.html$")
DEFAULT_DELAY = 1.0
MAX_PAGES = 20
MAX_THREAD_PAGES = 50


def fail(message: str) -> int:
    print(json.dumps({"status": "error", "error": message}, ensure_ascii=False), file=sys.stderr)
    return 1


def assert_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"52pojie.cn", "www.52pojie.cn"}:
        raise ValueError("only public www.52pojie.cn URLs are supported")
    if parsed.path in {"/search.php", "/member.php", "/home.php", "/api.php", "/misc.php"}:
        raise ValueError("the requested path is outside the public read scope")
    if parsed.path == "/forum.php":
        query = parse_qs(parsed.query)
        if query.get("mod") == ["rss"]:
            return
        if query.get("mod") == ["guide"] and query.get("view") == ["hot"]:
            return
        raise ValueError("only public forum.php RSS and guide-hot pages are supported")


def decode_body(data: bytes, content_type: str = "") -> str:
    match = re.search(r"charset\s*=\s*['\"]?([\w-]+)", content_type, re.I)
    candidates = [match.group(1)] if match else []
    candidates.extend(["utf-8", "gbk", "gb18030"])
    for encoding in candidates:
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("gb18030", errors="replace")


def fetch(url: str, delay: float, timeout: int = 30) -> str:
    assert_public_url(url)
    if delay > 0:
        time.sleep(delay)
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xml"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return decode_body(response.read(), response.headers.get("Content-Type", ""))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"fetch failed for {url}: {exc}") from exc


def text_value(value: str) -> str:
    value = re.sub(r"\s+", " ", value.replace("\xa0", " "))
    return value.strip()


def body_text(value: str) -> str:
    lines = [text_value(line) for line in value.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def extract_page_count(source: str) -> int:
    patterns = (
        r"<label[^>]*>.*?/\s*(\d+)\s*页",
        r"共\s*(\d+)\s*页",
    )
    for pattern in patterns:
        match = re.search(pattern, source, re.I | re.S)
        if match:
            return max(int(match.group(1)), 1)
    return 1


class ForumListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.current: dict[str, Any] | None = None
        self.threads: list[dict[str, str]] = []
        self.seen: set[str] = set()
        self.title: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag != "a":
            return
        href = values.get("href") or ""
        match = THREAD_PATH.match(href.split("?", 1)[0].lstrip("./"))
        classes = set((values.get("class") or "").split())
        if match and ("xst" in classes or "s" in classes):
            tid = match.group("tid")
            if tid not in self.seen:
                self.current = {"tid": tid, "url": urljoin(BASE_URL, href), "title": ""}

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title.append(data)
        if self.current is not None:
            self.current["title"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag == "a" and self.current is not None:
            item = dict(self.current)
            item["title"] = text_value(item["title"])
            if item["title"]:
                self.threads.append(item)
                self.seen.add(item["tid"])
            self.current = None


class ThreadParser(HTMLParser):
    BLOCK_TAGS = {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "pre"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page_title: list[str] = []
        self.subject: list[str] = []
        self.author: list[str] = []
        self.posted_at: list[str] = []
        self.message: list[str] = []
        self.in_page_title = False
        self.capture: dict[str, Any] | None = None
        self.capture_depth = 0
        self.ignore_depth = 0
        self.posts: list[dict[str, Any]] = []
        self.attachments: list[dict[str, str]] = []

    @staticmethod
    def attr_map(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key: value or "" for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = self.attr_map(attrs)
        element_id = values.get("id", "")
        classes = set(values.get("class", "").split())
        if tag == "title":
            self.in_page_title = True
        if tag in {"script", "style", "noscript"} and self.capture is not None:
            self.ignore_depth += 1
        if element_id == "thread_subject":
            self.capture = {"kind": "subject", "text": [], "depth": 1}
            self.capture_depth = 1
        elif element_id.startswith("postmessage_"):
            post_id = element_id.removeprefix("postmessage_")
            self.capture = {"kind": "post", "post_id": post_id, "text": [], "depth": 1}
            self.capture_depth = 1
        elif "res-author" in classes:
            self.capture = {"kind": "author", "text": [], "depth": 1}
            self.capture_depth = 1
        elif element_id.startswith("authorposton"):
            self.capture = {"kind": "posted_at", "text": [], "depth": 1}
            self.capture_depth = 1
        elif element_id == "messagetext":
            self.capture = {"kind": "message", "text": [], "depth": 1}
            self.capture_depth = 1
        elif self.capture is not None:
            self.capture_depth += 1
        if "file" in values or "zoomfile" in values:
            url = values.get("file") or values.get("zoomfile")
            if url:
                self.attachments.append({"url": urljoin(BASE_URL, url), "aid": values.get("aid", "")})

    def handle_data(self, data: str) -> None:
        if self.in_page_title:
            self.page_title.append(data)
        if self.capture is None or self.ignore_depth:
            return
        self.capture["text"].append(data)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_page_title = False
        if tag in {"script", "style", "noscript"} and self.ignore_depth:
            self.ignore_depth -= 1
        if self.capture is None:
            return
        if tag in self.BLOCK_TAGS:
            self.capture["text"].append("\n")
        self.capture_depth -= 1
        if self.capture_depth > 0:
            return
        captured = self.capture
        self.capture = None
        value = body_text("".join(captured["text"]))
        if captured["kind"] == "subject":
            self.subject.append(value)
        elif captured["kind"] == "author":
            self.author.append(value)
        elif captured["kind"] == "posted_at":
            self.posted_at.append(value)
        elif captured["kind"] == "message":
            self.message.append(value)
        elif captured["kind"] == "post":
            self.posts.append({"post_id": captured["post_id"], "text": value})


def parse_listing(
    url: str,
    source: str,
    fid: int | None,
    page: int,
    view: str = "forum",
) -> dict[str, Any]:
    parser = ForumListingParser()
    parser.feed(source)
    return {
        "kind": "forum_listing",
        "source_url": url,
        "fid": fid,
        "page": page,
        "view": view,
        "page_count": extract_page_count(source),
        "threads": parser.threads,
        "page_title": text_value("".join(parser.title)),
    }


def parse_rss(url: str, source: str, fid: int) -> dict[str, Any]:
    try:
        root = ElementTree.fromstring(source)
    except ElementTree.ParseError as exc:
        raise RuntimeError(f"RSS parse failed: {exc}") from exc
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("RSS response has no channel")

    def child_text(parent: ElementTree.Element, name: str) -> str:
        node = parent.find(name)
        return text_value(node.text or "") if node is not None else ""

    items = []
    for item in channel.findall("item"):
        items.append({
            "title": child_text(item, "title"),
            "url": child_text(item, "link"),
            "description": child_text(item, "description"),
            "category": child_text(item, "category"),
            "author": child_text(item, "author"),
            "published_at": child_text(item, "pubDate"),
        })
    return {
        "kind": "forum_rss",
        "source_url": url,
        "fid": fid,
        "channel": child_text(channel, "title"),
        "last_build_date": child_text(channel, "lastBuildDate"),
        "items": items,
    }


def parse_thread(url: str, source: str, tid: int, page: int) -> dict[str, Any]:
    parser = ThreadParser()
    parser.feed(source)
    return {
        "kind": "thread",
        "source_url": url,
        "tid": tid,
        "page": page,
        "page_count": extract_page_count(source),
        "page_title": text_value("".join(parser.page_title)),
        "subject": text_value(" ".join(parser.subject)),
        "author": text_value(" ".join(parser.author)),
        "posted_at": text_value(" ".join(parser.posted_at)),
        "message": text_value(" ".join(parser.message)),
        "content_status": (
            "ok"
            if parser.posts or parser.subject
            else "restricted"
            if parser.message
            else "empty"
        ),
        "posts": [{**post, "page": page} for post in parser.posts],
        "attachments": parser.attachments,
    }


def forum_url(fid: int, page: int) -> str:
    return f"{BASE_URL}forum-{fid}-{page}.html"


def rss_url(fid: int) -> str:
    return f"{BASE_URL}forum.php?mod=rss&fid={fid}"


def hot_url(page: int = 1) -> str:
    suffix = "" if page == 1 else f"&page={page}"
    return f"{BASE_URL}forum.php?mod=guide&view=hot{suffix}"


def thread_url(tid: int, page: int) -> str:
    return f"{BASE_URL}thread-{tid}-{page}-1.html"


def command_list(args: argparse.Namespace) -> dict[str, Any]:
    url = forum_url(args.fid, args.page)
    return parse_listing(url, fetch(url, args.delay), args.fid, args.page)


def command_rss(args: argparse.Namespace) -> dict[str, Any]:
    url = rss_url(args.fid)
    return parse_rss(url, fetch(url, args.delay), args.fid)


def command_hot(args: argparse.Namespace) -> dict[str, Any]:
    page = getattr(args, "page", 1)
    url = hot_url(page)
    return parse_listing(url, fetch(url, args.delay), None, page, view="hot")


def command_thread(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "all_pages", False):
        return read_thread_pages(args)
    return fetch_thread_page(args)


def fetch_thread_page(args: argparse.Namespace) -> dict[str, Any]:
    url = thread_url(args.tid, args.page)
    return parse_thread(url, fetch(url, args.delay), args.tid, args.page)


def read_thread_pages(args: argparse.Namespace) -> dict[str, Any]:
    first = fetch_thread_page(args)
    if not args.all_pages:
        first["pages_read"] = [args.page]
        first["truncated"] = first["page_count"] > args.page
        return first

    last_page = min(first["page_count"], MAX_THREAD_PAGES, max(args.max_thread_pages, 1))
    pages = [first]
    for page in range(args.page + 1, last_page + 1):
        page_args = argparse.Namespace(tid=args.tid, page=page, delay=args.delay)
        pages.append(fetch_thread_page(page_args))

    merged = dict(first)
    merged["posts"] = []
    merged["attachments"] = []
    seen_posts: set[str] = set()
    seen_attachments: set[tuple[str, str]] = set()
    for item in pages:
        for post in item["posts"]:
            if post["post_id"] not in seen_posts:
                merged["posts"].append(post)
                seen_posts.add(post["post_id"])
        for attachment in item["attachments"]:
            key = (attachment.get("aid", ""), attachment.get("url", ""))
            if key not in seen_attachments:
                merged["attachments"].append(attachment)
                seen_attachments.add(key)
    merged["pages_read"] = [item["page"] for item in pages]
    merged["truncated"] = last_page < first["page_count"]
    return merged


def text_snippet(value: str, query: str, radius: int = 90) -> str:
    folded = value.casefold()
    position = folded.find(query.casefold())
    if position < 0:
        return ""
    start = max(position - radius, 0)
    end = min(position + len(query) + radius, len(value))
    snippet = text_value(value[start:end])
    if start:
        snippet = "..." + snippet
    if end < len(value):
        snippet += "..."
    return snippet


def thread_matches(thread: dict[str, Any], query: str) -> list[dict[str, Any]]:
    matches = []
    for post in thread["posts"]:
        snippet = text_snippet(post.get("text", ""), query)
        if snippet:
            matches.append({
                "post_id": post["post_id"],
                "page": post.get("page", thread["page"]),
                "snippet": snippet,
            })
    return matches


def command_search(args: argparse.Namespace) -> dict[str, Any]:
    query = args.query.casefold()
    pages = min(max(args.pages, 1), MAX_PAGES)
    matches: list[dict[str, Any]] = []
    listing_threads: list[dict[str, str]] = []
    for page in range(1, pages + 1):
        listing = command_list(argparse.Namespace(fid=args.fid, page=page, delay=args.delay))
        listing_threads.extend({**item, "listing_page": page} for item in listing["threads"])
        for item in listing["threads"]:
            if query in item["title"].casefold():
                matches.append({**item, "matched_in": "title", "listing_page": page})
    feed = command_rss(argparse.Namespace(fid=args.fid, delay=args.delay)) if args.include_rss else None
    if feed:
        for item in feed["items"]:
            searchable = f"{item['title']}\n{item['description']}".casefold()
            if query in searchable and not any(existing.get("url") == item["url"] for existing in matches):
                matches.append({**item, "matched_in": "rss"})
    if args.include_hot:
        hot = command_hot(argparse.Namespace(delay=args.delay))
        for item in hot["threads"]:
            if query in item["title"].casefold() and not any(existing.get("url") == item["url"] for existing in matches):
                matches.append({**item, "matched_in": "hot"})

    body_scan_count = 0
    body_scan_truncated = False
    body_scan_errors: list[dict[str, str]] = []
    if args.scan_thread_bodies:
        body_candidates = []
        seen_urls: set[str] = set()
        for item in listing_threads:
            if item["url"] not in seen_urls:
                body_candidates.append(item)
                seen_urls.add(item["url"])
        body_limit = max(args.max_body_threads, 0)
        body_scan_truncated = len(body_candidates) > body_limit
        for item in body_candidates[:body_limit]:
            tid_match = re.search(r"thread-(\d+)-", item.get("url", ""))
            if not tid_match:
                continue
            body_scan_count += 1
            try:
                detail = read_thread_pages(argparse.Namespace(
                    tid=int(tid_match.group(1)),
                    page=1,
                    delay=args.delay,
                    all_pages=args.all_thread_pages,
                    max_thread_pages=args.max_thread_pages,
                ))
                hits = thread_matches(detail, args.query)
                if not hits:
                    continue
                existing = next((candidate for candidate in matches if candidate.get("url") == item["url"]), None)
                if existing is None:
                    existing = {**item, "matched_in": "thread"}
                    matches.append(existing)
                existing["thread_page_count"] = detail["page_count"]
                existing["thread_pages_read"] = detail["pages_read"]
                existing["thread_truncated"] = detail["truncated"]
                existing["thread_content_status"] = detail["content_status"]
                existing["thread_message"] = detail["message"]
                existing["thread_matches"] = hits
            except (RuntimeError, ValueError) as exc:
                body_scan_errors.append({"url": item["url"], "error": str(exc)})

    if args.read_threads:
        for item in matches[: max(args.max_thread_results, 0)]:
            tid_match = re.search(r"thread-(\d+)-", item.get("url", ""))
            if not tid_match:
                continue
            try:
                detail = read_thread_pages(argparse.Namespace(
                    tid=int(tid_match.group(1)),
                    page=1,
                    delay=args.delay,
                    all_pages=args.all_thread_pages,
                    max_thread_pages=args.max_thread_pages,
                ))
                item["thread_page_count"] = detail["page_count"]
                item["thread_pages_read"] = detail["pages_read"]
                item["thread_truncated"] = detail["truncated"]
                item["thread_content_status"] = detail["content_status"]
                item["thread_message"] = detail["message"]
                item["thread_matches"] = thread_matches(detail, args.query)
            except (RuntimeError, ValueError) as exc:
                item["thread_error"] = str(exc)
    return {
        "kind": "forum_search",
        "query": args.query,
        "fid": args.fid,
        "pages_scanned": pages,
        "search_scope": "public listing titles, optional RSS descriptions, and optionally selected thread bodies",
        "body_scan_threads": body_scan_count,
        "body_scan_truncated": body_scan_truncated,
        "body_scan_errors": body_scan_errors,
        "matches": matches,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read public 52pojie forum pages")
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="read one public forum listing page")
    list_parser.add_argument("--fid", type=int, default=4)
    list_parser.add_argument("--page", type=int, default=1)
    list_parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    list_parser.set_defaults(handler=command_list)

    rss_parser = sub.add_parser("rss", help="read a public forum RSS feed")
    rss_parser.add_argument("--fid", type=int, default=4)
    rss_parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    rss_parser.set_defaults(handler=command_rss)

    hot_parser = sub.add_parser("hot", help="read the public hot-guide listing")
    hot_parser.add_argument("--page", type=int, default=1)
    hot_parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    hot_parser.set_defaults(handler=command_hot)

    thread_parser = sub.add_parser("thread", help="read one public thread page")
    thread_parser.add_argument("--tid", type=int, required=True)
    thread_parser.add_argument("--page", type=int, default=1)
    thread_parser.add_argument("--all-pages", action=argparse.BooleanOptionalAction, default=False)
    thread_parser.add_argument("--max-thread-pages", type=int, default=MAX_THREAD_PAGES)
    thread_parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    thread_parser.set_defaults(handler=command_thread)

    search_parser = sub.add_parser("search", help="filter public listing pages and RSS")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--fid", type=int, default=4)
    search_parser.add_argument("--pages", type=int, default=3)
    search_parser.add_argument("--include-rss", action=argparse.BooleanOptionalAction, default=True)
    search_parser.add_argument("--include-hot", action=argparse.BooleanOptionalAction, default=False)
    search_parser.add_argument("--read-threads", action=argparse.BooleanOptionalAction, default=False)
    search_parser.add_argument("--scan-thread-bodies", action=argparse.BooleanOptionalAction, default=False)
    search_parser.add_argument("--max-body-threads", type=int, default=10)
    search_parser.add_argument("--max-thread-results", type=int, default=10)
    search_parser.add_argument("--all-thread-pages", action=argparse.BooleanOptionalAction, default=False)
    search_parser.add_argument("--max-thread-pages", type=int, default=MAX_THREAD_PAGES)
    search_parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    search_parser.set_defaults(handler=command_search)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = args.handler(args)
    except (RuntimeError, ValueError) as exc:
        return fail(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
