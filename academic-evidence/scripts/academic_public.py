#!/usr/bin/env python3
"""Retrieve public paper metadata, abstracts, and selected HTML body passages."""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from html import unescape
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from typing import Any


USER_AGENT = "research-router/academic-public"
TIMEOUT = 20.0
MAX_RESPONSE_BYTES = 8_000_000
MAX_TEXT_CHARS = 24_000
ATOM = "http://www.w3.org/2005/Atom"
ARXIV_ID = re.compile(r"(?:arxiv\.org/(?:abs|pdf|html)/)(\d{4}\.\d{4,5}(?:v\d+)?)", re.I)


class AcademicError(RuntimeError):
    pass


def fetch(url: str, accept: str = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8") -> bytes:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or "." not in parsed.hostname:
        raise AcademicError("URL must point to a public HTTP or HTTPS host")
    if parsed.hostname.lower() in {"localhost", "localhost.localdomain"} or parsed.hostname.endswith(".local"):
        raise AcademicError("local hostnames are not supported")
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raise AcademicError(f"HTTP {exc.code} from {url}") from exc
    except (URLError, TimeoutError) as exc:
        raise AcademicError(f"public request failed for {url}: {exc}") from exc
    if len(payload) > MAX_RESPONSE_BYTES:
        raise AcademicError(f"public response exceeded {MAX_RESPONSE_BYTES} bytes")
    return payload


def arxiv_metadata(identifier: str) -> dict[str, Any]:
    identifier = identifier.removeprefix("arXiv:")
    payload = fetch(
        "https://export.arxiv.org/api/query?id_list=" + quote(identifier, safe="."),
        "application/atom+xml",
    )
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise AcademicError("arXiv returned invalid Atom XML") from exc
    entry = root.find(f"{{{ATOM}}}entry")
    if entry is None:
        raise AcademicError(f"arXiv returned no record for {identifier}")
    def text(tag: str) -> str:
        node = entry.find(f"{{{ATOM}}}{tag}")
        return " ".join((node.text or "").split()) if node is not None else ""
    authors = [
        " ".join((node.findtext(f"{{{ATOM}}}name") or "").split())
        for node in entry.findall(f"{{{ATOM}}}author")
    ]
    published = text("published")
    base = f"https://arxiv.org/abs/{identifier}"
    return {
        "status": "ok",
        "source": "arxiv-atom-api",
        "arxiv_id": identifier,
        "title": text("title"),
        "authors": [author for author in authors if author],
        "published_at": published or None,
        "abstract": text("summary"),
        "categories": [item.attrib.get("term") for item in entry.findall(f"{{{ATOM}}}{{http://arxiv.org/schemas/atom}}category")],
        "url": base,
        "html_url": f"https://arxiv.org/html/{identifier}",
        "pdf_url": f"https://arxiv.org/pdf/{identifier}",
        "evidence_level": "metadata",
    }


def crossref_metadata(doi: str) -> dict[str, Any]:
    url = "https://api.crossref.org/works/" + quote(doi.strip(), safe="")
    try:
        payload = json.loads(fetch(url, "application/json").decode("utf-8"))
        item = payload["message"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise AcademicError("Crossref returned invalid work metadata") from exc
    titles = item.get("title") or []
    dates = item.get("published-print") or item.get("published-online") or item.get("issued") or {}
    date_parts = dates.get("date-parts") or [[]]
    authors = []
    for author in item.get("author") or []:
        name = " ".join(part for part in (author.get("given"), author.get("family")) if part)
        if name:
            authors.append(name)
    abstract = item.get("abstract") or ""
    return {
        "status": "ok",
        "source": "crossref-api",
        "doi": item.get("DOI", doi),
        "title": unescape(re.sub(r"<[^>]+>", " ", titles[0])).strip() if titles else "",
        "authors": authors,
        "published_date_parts": date_parts[0] if date_parts else [],
        "venue": (item.get("container-title") or [""])[0],
        "type": item.get("type"),
        "abstract": unescape(re.sub(r"<[^>]+>", " ", abstract)).strip() if abstract else "",
        "url": item.get("URL") or f"https://doi.org/{quote(doi, safe='/')}",
        "evidence_level": "metadata",
    }


class PaperPageParser(HTMLParser):
    SKIP = {"script", "style", "nav", "footer", "header", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, list[str]] = {}
        self.title = ""
        self.paragraphs: list[str] = []
        self.headings: list[str] = []
        self.stack: list[str] = []
        self.skip_depth = 0
        self.capture_tag: str | None = None
        self.capture_depth = -1
        self.capture_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        if tag == "meta":
            key = (attrs_map.get("name") or attrs_map.get("property") or "").lower()
            content = attrs_map.get("content") or ""
            if key and content:
                self.meta.setdefault(key, []).append(" ".join(content.split()))
        if tag in self.SKIP:
            self.skip_depth += 1
        depth = len(self.stack)
        if not self.skip_depth and tag in {"title", "p", "h1", "h2", "h3", "h4", "h5", "h6", "abstract"} and self.capture_tag is None:
            self.capture_tag = tag
            self.capture_depth = depth
            self.capture_parts = []
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(tag)

    def handle_data(self, data: str) -> None:
        if self.capture_tag is not None and not self.skip_depth:
            self.capture_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack:
            return
        depth = len(self.stack) - 1
        if self.capture_tag == tag and self.capture_depth == depth:
            text = " ".join(" ".join(self.capture_parts).split())
            if tag == "title":
                self.title = text
            elif tag.startswith("h"):
                if text:
                    self.headings.append(text[:240])
            elif text:
                self.paragraphs.append(text[:3000])
            self.capture_tag = None
            self.capture_depth = -1
            self.capture_parts = []
        if tag in self.SKIP:
            self.skip_depth = max(0, self.skip_depth - 1)
        self.stack.pop()

    def metadata_value(self, *names: str) -> str:
        for name in names:
            values = self.meta.get(name.lower()) or []
            if values and values[0].strip():
                return values[0].strip()
        return ""


def read_html(url: str, terms: list[str], max_paragraphs: int) -> dict[str, Any]:
    payload = fetch(url)
    parser = PaperPageParser()
    parser.feed(payload.decode("utf-8", errors="replace"))
    parser.close()
    title = parser.metadata_value("citation_title", "dc.title", "og:title") or parser.title
    abstract = parser.metadata_value("citation_abstract", "dc.description", "description", "og:description")
    lowered_terms = [term.casefold().strip() for term in terms if term.strip()]
    if lowered_terms:
        selected = [
            paragraph for paragraph in parser.paragraphs
            if any(term in paragraph.casefold() for term in lowered_terms)
        ]
    else:
        selected = parser.paragraphs
    selected = selected[:max_paragraphs]
    all_text = "\n\n".join(selected)
    truncated = len(all_text) > MAX_TEXT_CHARS
    if truncated:
        all_text = all_text[:MAX_TEXT_CHARS]
    authors = parser.meta.get("citation_author", [])
    return {
        "status": "ok" if (abstract or selected) else "partial",
        "retrieval_stage": "paper-body",
        "url": url,
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "headings": parser.headings[:160],
        "selected_passages": selected,
        "terms": terms,
        "truncated": truncated,
        "evidence_level": "public-html-body" if selected else "metadata",
        "limits": ["HTML extraction only; exact quotations and claims must be reviewed against the cited source page."],
    }


def paper_read(url: str, terms: list[str], max_paragraphs: int) -> dict[str, Any]:
    match = ARXIV_ID.search(url)
    if not match:
        return read_html(url, terms, max_paragraphs)
    identifier = match.group(1)
    urls = [f"https://arxiv.org/html/{identifier}", f"https://ar5iv.labs.arxiv.org/html/{identifier}"]
    failures = []
    for candidate in urls:
        try:
            result = read_html(candidate, terms, max_paragraphs)
            result["arxiv_id"] = identifier
            result["abstract_url"] = f"https://arxiv.org/abs/{identifier}"
            return result
        except AcademicError as exc:
            failures.append(str(exc))
    metadata = arxiv_metadata(identifier)
    return {
        "status": "partial",
        "retrieval_stage": "paper-brief",
        "url": metadata["url"],
        "title": metadata["title"],
        "authors": metadata["authors"],
        "abstract": metadata["abstract"],
        "pdf_url": metadata["pdf_url"],
        "evidence_level": "abstract-only",
        "limits": ["arXiv HTML full text was unavailable", *failures],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)
    metadata = subparsers.add_parser("metadata")
    source = metadata.add_mutually_exclusive_group(required=True)
    source.add_argument("--doi")
    source.add_argument("--arxiv")
    source.add_argument("--url")
    read = subparsers.add_parser("read")
    read.add_argument("--url", required=True)
    read.add_argument("--term", action="append", default=[])
    read.add_argument("--max-paragraphs", type=int, default=30)
    args = parser.parse_args()
    if args.mode == "read" and not 1 <= args.max_paragraphs <= 100:
        parser.error("--max-paragraphs must be 1..100")
    try:
        if args.mode == "metadata":
            if args.doi:
                result = crossref_metadata(args.doi)
            elif args.arxiv:
                result = arxiv_metadata(args.arxiv)
            else:
                result = read_html(args.url, [], 1)
                result = {key: result.get(key) for key in ("status", "url", "title", "authors", "abstract", "evidence_level")}
        else:
            result = paper_read(args.url, args.term, args.max_paragraphs)
    except (AcademicError, ValueError) as exc:
        print(json.dumps({"status": "unavailable", "mode": args.mode, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
