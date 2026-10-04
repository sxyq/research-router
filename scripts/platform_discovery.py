#!/usr/bin/env python3
"""Find public platform-domain pages through a bounded no-key web search."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from html import unescape
from html.parser import HTMLParser
import xml.etree.ElementTree as ET
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_REGISTRY = ROOT / "registry" / "platform-domains.json"
ENDPOINT = "https://html.duckduckgo.com/html/"
BING_ENDPOINT = "https://www.bing.com/search"
USER_AGENT = "research-router/platform-discovery"
TIMEOUT = 15.0
MAX_RESPONSE_BYTES = 2_000_000


class DiscoveryError(RuntimeError):
    pass


class ResultsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str | None]] = []
        self.capture_kind: str | None = None
        self.capture_tag: str | None = None
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if self.capture_tag is not None:
            return
        if tag == "a" and "result__a" in classes:
            href = values.get("href") or ""
            parsed = urlparse(href)
            target = parse_qs(parsed.query).get("uddg", [href])[0]
            self.results.append({"title": "", "url": urljoin(ENDPOINT, unescape(target)), "excerpt": ""})
            self.capture_kind = "title"
            self.capture_tag = tag
            self.parts = []
        elif tag in {"a", "div", "span"} and "result__snippet" in classes and self.results:
            self.capture_kind = "excerpt"
            self.capture_tag = tag
            self.parts = []

    def handle_data(self, data: str) -> None:
        if self.capture_tag is not None:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.capture_tag != tag:
            return
        if self.capture_kind == "title":
            if self.results:
                self.results[-1]["title"] = " ".join(" ".join(self.parts).split())
            self.capture_kind = None
            self.capture_tag = None
            self.parts = []
        elif self.capture_kind == "excerpt":
            if self.results:
                self.results[-1]["excerpt"] = " ".join(" ".join(self.parts).split())
            self.capture_kind = None
            self.capture_tag = None
            self.parts = []


def load_domains() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(DOMAIN_REGISTRY.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DiscoveryError(f"cannot read platform domain Registry: {exc}") from exc
    mappings = data.get("platforms") if isinstance(data, dict) else None
    if not isinstance(mappings, dict):
        raise DiscoveryError("platform-domains.json must contain a platforms object")
    result: dict[str, dict[str, Any]] = {}
    for platform_id, entry in mappings.items():
        domains = entry.get("domains") if isinstance(entry, dict) else None
        if not isinstance(domains, list) or not all(isinstance(domain, str) for domain in domains):
            raise DiscoveryError(f"invalid domain list for {platform_id}")
        result[platform_id] = entry
    return result


def native_search(provider: str, platform_id: str, queries: list[str], limit: int, timeout: float, base_url: str | None) -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location("research_router_fast_search", ROOT / "scripts" / "fast_search.py")
    if spec is None or spec.loader is None:
        raise DiscoveryError("bundled fast-search provider could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if provider == "discourse" and not base_url:
        raise DiscoveryError(f"{platform_id} needs its public Discourse base URL")
    results: list[dict[str, Any]] = []
    failures: list[str] = []
    for query in queries:
        args = SimpleNamespace(
            query=query,
            limit=limit,
            timeout=timeout,
            page=1,
            category=None,
            tag=None,
            base_url=base_url,
            language="en",
        )
        try:
            rows = module.SEARCHERS[provider](args)
        except module.SearchError as exc:
            failures.append(str(exc))
            continue
        for row in rows:
            result = dict(row)
            result["platform_id"] = platform_id
            results.append(result)
    return {
        "status": "ok" if results and not failures else "partial" if results or not failures else "unavailable",
        "platform_id": platform_id,
        "provider": provider,
        "queries": queries,
        "results": results,
        "evidence_level": "discovery" if results else "none",
        "failures": failures,
    }


def _normalize_result(platform_id: str, domain: str, query: str, title: str, url: str, excerpt: str, published_at: str | None, provider: str) -> dict[str, Any]:
    return {
        "title": title,
        "url": url,
        "excerpt": excerpt,
        "published_at": published_at,
        "source": provider,
        "platform_id": platform_id,
        "domain": domain,
        "query": query,
        "evidence_level": "discovery",
    }


def search_bing_rss(platform_id: str, domain: str, query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
    search_query = f"site:{domain} {query}".strip()
    request = Request(
        BING_ENDPOINT + "?" + urlencode({"q": search_query, "format": "rss"}),
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml,application/xml,text/xml"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raise DiscoveryError(f"Bing public RSS HTTP {exc.code} for domain {domain}") from exc
    except (URLError, TimeoutError) as exc:
        raise DiscoveryError(f"Bing public RSS failed for domain {domain}: {exc}") from exc
    if len(payload) > MAX_RESPONSE_BYTES:
        raise DiscoveryError(f"Bing public RSS response exceeded {MAX_RESPONSE_BYTES} bytes")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise DiscoveryError("Bing public RSS returned invalid XML") from exc
    items = root.findall(".//item")
    return [
        _normalize_result(
            platform_id,
            domain,
            query,
            " ".join((item.findtext("title") or "").split()),
            (item.findtext("link") or "").strip(),
            " ".join((item.findtext("description") or "").split()),
            (item.findtext("pubDate") or "").strip() or None,
            "bing-public-rss",
        )
        for item in items[:limit]
        if (item.findtext("link") or "").strip()
    ]


def search_duckduckgo_html(platform_id: str, domain: str, query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
    search_query = f"site:{domain} {query}".strip()
    request = Request(
        ENDPOINT + "?" + urlencode({"q": search_query, "kl": "us-en"}),
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raise DiscoveryError(f"DuckDuckGo HTML HTTP {exc.code} for domain {domain}") from exc
    except (URLError, TimeoutError) as exc:
        raise DiscoveryError(f"DuckDuckGo HTML failed for domain {domain}: {exc}") from exc
    if len(payload) > MAX_RESPONSE_BYTES:
        raise DiscoveryError(f"DuckDuckGo HTML response exceeded {MAX_RESPONSE_BYTES} bytes")
    document = payload.decode("utf-8", errors="replace")
    lowered = document.lower()
    if any(marker in lowered for marker in ("captcha", "anomaly-modal", "botnet", "automated requests")):
        raise DiscoveryError("DuckDuckGo HTML returned a challenge page")
    parser = ResultsParser()
    parser.feed(document)
    parser.close()
    results = []
    for item in parser.results:
        url = str(item.get("url") or "")
        if urlparse(url).scheme not in {"http", "https"}:
            continue
        results.append(_normalize_result(platform_id, domain, query, item.get("title") or "", url, item.get("excerpt") or "", None, "duckduckgo-html"))
        if len(results) >= limit:
            break
    return results


def search_one(platform_id: str, domain: str, query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
    def scoped(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        expected = domain.lower().strip(".")
        selected = []
        for row in rows:
            host = (urlparse(str(row.get("url") or "")).hostname or "").lower().strip(".")
            if host == expected or host.endswith("." + expected):
                selected.append(row)
        return selected

    try:
        results = scoped(search_bing_rss(platform_id, domain, query, limit, timeout))
        if results:
            return results
    except DiscoveryError as bing_error:
        errors = [str(bing_error)]
    else:
        errors = []
    try:
        results = scoped(search_duckduckgo_html(platform_id, domain, query, limit, timeout))
        if results:
            return results
        errors.append("DuckDuckGo returned no candidates on the registered domain")
    except DiscoveryError as ddg_error:
        errors.append(str(ddg_error))
    if errors:
        raise DiscoveryError("Public search backends unavailable or returned no domain-matched candidates: " + "; ".join(errors))
    return []


def discover(
    platform_id: str,
    queries: list[str],
    limit: int,
    timeout: float,
    base_url: str | None = None,
) -> dict[str, Any]:
    entry = load_domains().get(platform_id)
    if entry is None:
        raise DiscoveryError(f"platform has no generic public discovery registration: {platform_id}")
    domains = entry["domains"]
    provider = entry.get("native_provider")
    if provider:
        effective_base = entry.get("base_url") or base_url
        return native_search(provider, platform_id, queries, limit, timeout, effective_base)
    if not domains:
        raise DiscoveryError(f"platform {platform_id} requires a platform-specific public endpoint")
    results: list[dict[str, Any]] = []
    failures: list[str] = []
    seen: set[str] = set()
    for query in queries:
        for domain in domains:
            try:
                candidates = search_one(platform_id, domain, query, limit, timeout)
            except DiscoveryError as exc:
                failures.append(str(exc))
                continue
            for item in candidates:
                url = item["url"]
                if url not in seen:
                    seen.add(url)
                    results.append(item)
    status = "ok" if results and not failures else "partial" if results or not failures else "unavailable"
    return {
        "status": status,
        "platform_id": platform_id,
        "provider": "public-domain-discovery",
        "domains": domains,
        "queries": queries,
        "results": results,
        "evidence_level": "discovery" if results else "none",
        "limits": ["Uses public site-constrained web discovery; does not access authenticated pages or platform APIs."],
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, help="Registered canonical platform id")
    parser.add_argument("--query", action="append", required=True, help="Agent-generated query; repeat as needed")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=TIMEOUT)
    parser.add_argument("--base-url", help="Public Discourse forum URL when one is not registered")
    args = parser.parse_args()
    if not 1 <= args.limit <= 20 or args.timeout <= 0:
        parser.error("limit must be 1..20 and timeout must be positive")
    try:
        result = discover(args.platform, args.query, args.limit, args.timeout, args.base_url)
    except DiscoveryError as exc:
        print(json.dumps({"status": "unavailable", "platform_id": args.platform, "provider": "public-web-site-search", "results": [], "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] != "unavailable" else 2


if __name__ == "__main__":
    raise SystemExit(main())
