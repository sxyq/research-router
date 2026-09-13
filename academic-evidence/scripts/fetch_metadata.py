#!/usr/bin/env python3
"""Normalize paper metadata from DOI and venue pages."""

from __future__ import annotations

import argparse
import html
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

UA = "research-router/academic-evidence/1.0"
CTX = ssl.create_default_context()
MONTHS = {
    "jan": "01",
    "feb": "02",
    "mar": "03",
    "apr": "04",
    "may": "05",
    "jun": "06",
    "jul": "07",
    "aug": "08",
    "sep": "09",
    "oct": "10",
    "nov": "11",
    "dec": "12",
}


def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30, context=CTX) as resp:
        return resp.read().decode("utf-8", errors="replace")


def read_manifest(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and data.get("num") is not None:
        return [data]
    if isinstance(data, dict) and isinstance(data.get("papers"), list):
        return data["papers"]
    raise ValueError("Manifest must be a JSON array, a single paper object, or an object with a 'papers' array.")


def write_manifest(path: Path, papers: list[dict]) -> None:
    path.write_text(json.dumps(papers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_authors(value):
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"\s*;\s*", value) if part.strip()]
    return []


def normalize_date(text: str) -> str | None:
    text = html.unescape(text)
    match = re.search(r"(\d{4})[-/](\d{1,2})(?:[-/]\d{1,2})?", text)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"
    match = re.search(
        r"(\d{4})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*",
        text,
        flags=re.I,
    )
    if match:
        return f"{int(match.group(1)):04d}-{MONTHS[match.group(2)[:3].lower()]}"
    match = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})",
        text,
        flags=re.I,
    )
    if match:
        return f"{int(match.group(2)):04d}-{MONTHS[match.group(1)[:3].lower()]}"
    return None


def crossref_metadata(doi: str) -> dict:
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    message = json.loads(http_get(url))["message"]
    out = {}
    titles = message.get("title") or []
    if titles:
        out["title"] = titles[0].strip()
    authors = []
    for author in message.get("author") or []:
        given = (author.get("given") or "").strip()
        family = (author.get("family") or "").strip()
        full = " ".join(part for part in [given, family] if part).strip()
        if full:
            authors.append(full)
    if authors:
        out["authors"] = authors
    for key in ["published-print", "published-online", "published", "issued", "created"]:
        parts = (message.get(key) or {}).get("date-parts") or []
        if parts and parts[0]:
            arr = parts[0]
            if len(arr) >= 2:
                out["published_ym"] = f"{arr[0]:04d}-{arr[1]:02d}"
                break
    return out


def html_meta(html_text: str, name: str) -> str | None:
    patterns = [
        rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']{re.escape(name)}["\']',
        rf'<meta[^>]+property=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(name)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.I)
        if match:
            return html.unescape(match.group(1)).strip()
    return None


def page_metadata(url: str) -> dict:
    html_text = http_get(url)
    out = {}
    title = (
        html_meta(html_text, "citation_title")
        or html_meta(html_text, "dc.title")
        or html_meta(html_text, "og:title")
    )
    if title:
        out["title"] = title
    authors = re.findall(
        r'<meta[^>]+name=["\']citation_author["\'][^>]+content=["\']([^"\']+)',
        html_text,
        flags=re.I,
    )
    authors = [html.unescape(a).strip() for a in authors if a.strip()]
    if authors:
        out["authors"] = authors
    date_candidates = [
        html_meta(html_text, "citation_publication_date"),
        html_meta(html_text, "citation_online_date"),
        html_meta(html_text, "citation_date"),
        html_meta(html_text, "dc.date"),
        html_meta(html_text, "article:published_time"),
    ]
    for value in date_candidates:
        if value:
            norm = normalize_date(value)
            if norm:
                out["published_ym"] = norm
                break
    if "published_ym" not in out:
        match = re.search(
            r"month\s*=\s*(?:\"|&#34;)?([A-Za-z]{3,9})(?:\"|&#34;)?\s*,\s*[\r\n ]*year\s*=\s*(?:\"|&#34;)?(\d{4})",
            html_text,
            flags=re.I,
        )
        if match:
            out["published_ym"] = f"{int(match.group(2)):04d}-{MONTHS[match.group(1)[:3].lower()]}"
    return out


def arxiv_metadata(url: str) -> dict:
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5})", url)
    if not match:
        return {}
    xml = http_get("https://export.arxiv.org/api/query?id_list=" + match.group(1))
    out = {}
    title = re.search(r"<title>(.*?)</title>", xml, flags=re.S)
    if title:
        cleaned = re.sub(r"\s+", " ", html.unescape(title.group(1))).strip()
        if cleaned.lower() != "arxiv query results":
            out["title"] = cleaned
    authors = re.findall(r"<name>(.*?)</name>", xml, flags=re.S)
    authors = [re.sub(r"\s+", " ", html.unescape(a)).strip() for a in authors if a.strip()]
    if authors:
        out["authors"] = authors
    published = re.search(r"<published>(\d{4})-(\d{2})-\d{2}T", xml)
    if published:
        out["published_ym"] = f"{published.group(1)}-{published.group(2)}"
    return out


def second_link_label(page_url: str) -> str:
    return "DOI" if page_url.startswith("https://doi.org/") or page_url.startswith("http://doi.org/") else "Page"


def merge_missing(base: dict, incoming: dict) -> dict:
    for key, value in incoming.items():
        if key == "authors":
            if not normalize_authors(base.get(key)):
                base[key] = value
            continue
        if not base.get(key):
            base[key] = value
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill literature manifest metadata from DOI and page sources.")
    parser.add_argument("manifest", type=Path, help="Path to the manifest JSON file.")
    parser.add_argument("--write", action="store_true", help="Write results back to the manifest file.")
    parser.add_argument("--stdout", action="store_true", help="Print normalized JSON to stdout.")
    args = parser.parse_args()

    papers = read_manifest(args.manifest)
    for paper in papers:
        if "page_url" in paper and paper["page_url"] and not paper.get("second_link_label"):
            paper["second_link_label"] = second_link_label(str(paper["page_url"]))
        if paper.get("doi"):
            try:
                merge_missing(paper, crossref_metadata(str(paper["doi"])))
            except Exception as exc:  # pragma: no cover - network failure path
                paper.setdefault("_notes", []).append(f"crossref failed: {exc}")
        page_url = str(paper.get("page_url") or "")
        if page_url:
            try:
                merge_missing(paper, page_metadata(page_url))
            except Exception as exc:  # pragma: no cover - network failure path
                paper.setdefault("_notes", []).append(f"page metadata failed: {exc}")
        pdf_url = str(paper.get("pdf_url") or "")
        if pdf_url and "published_ym" not in paper:
            try:
                merge_missing(paper, arxiv_metadata(pdf_url))
            except Exception as exc:  # pragma: no cover - network failure path
                paper.setdefault("_notes", []).append(f"arxiv metadata failed: {exc}")
        if normalize_authors(paper.get("authors")):
            paper["authors"] = normalize_authors(paper.get("authors"))

    if args.write:
        write_manifest(args.manifest, papers)
    if args.stdout or not args.write:
        json.dump(papers, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
