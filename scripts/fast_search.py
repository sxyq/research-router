#!/usr/bin/env python3
"""Run compact research searches through public endpoints.

The script intentionally returns discovery records instead of raw pages. Use a
platform-specific reader or a selected source URL for the next evidence step.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
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
    headers: dict[str, str] | None = None,
) -> bytes:
    endpoint = url
    if params:
        url = f"{url}?{urlencode(params, doseq=True)}"
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept, **(headers or {})},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except HTTPError as exc:
        retry_after = exc.headers.get("Retry-After")
        suffix = f"; retry-after={retry_after}" if retry_after else ""
        raise SearchError(f"HTTP {exc.code} from {endpoint}{suffix}") from exc
    except URLError as exc:
        raise SearchError(f"network error for {endpoint}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise SearchError(f"timeout for {endpoint}") from exc


def request_json(
    url: str,
    params: dict[str, object] | None,
    timeout: float,
    headers: dict[str, str] | None = None,
) -> dict | list:
    payload = request_bytes(url, params, timeout, headers=headers)
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
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "title": clean_text(title, 240),
        "url": str(url or ""),
        "published_at": published_at,
        "excerpt": clean_text(excerpt),
        "source": source,
        "match_reason": match_reason or f"public search match for: {query}",
        "evidence_level": "discovery",
    }
    if extra:
        result.update(extra)
    return result


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
    api_key = os.environ.get("OPENALEX_API_KEY")
    params = {"search": args.query, "per_page": args.limit}
    params.update({"cursor": args.cursor} if args.cursor else {"page": args.page})
    filters = [f"{key}:{value}" for key, value in
               (("from_publication_date", args.from_date), ("to_publication_date", args.until_date)) if value]
    if filters:
        params["filter"] = ",".join(filters)
    data = request_json(
        "https://api.openalex.org/works",
        params,
        args.timeout,
        headers={"Authorization": f"Bearer {api_key}"} if api_key else None,
    )
    args.search_metadata = {
        key: value for key, value in data["meta"].items()
        if key in {"count", "page", "per_page", "cost_usd", "next_cursor"}
    }
    if args.cursor:
        args.search_metadata["cursor"] = args.cursor
        args.search_metadata["has_more"] = bool(data.get("results") and data["meta"].get("next_cursor"))
    else:
        args.search_metadata["has_more"] = args.page * args.limit < data["meta"]["count"]
        args.search_metadata["next_page"] = args.page + 1 if args.search_metadata["has_more"] else None
    results = []
    for item in data.get("results", [])[: args.limit]:
        location = item.get("primary_location") or {}
        source = location.get("source") or {}
        authors = [
            (author.get("author") or {}).get("display_name", "")
            for author in item.get("authorships", [])
        ]
        abstract_index = item.get("abstract_inverted_index") or {}
        abstract = ""
        if isinstance(abstract_index, dict):
            indexed_words = sorted(
                ((position, word) for word, positions in abstract_index.items() for position in positions),
                key=lambda pair: pair[0],
            )
            abstract = " ".join(word for _, word in indexed_words)
        best_location = item.get("best_oa_location") or location
        best_source = (best_location.get("source") or {}) if isinstance(best_location, dict) else {}
        results.append(
            record(
                item.get("title"),
                location.get("landing_page_url") or item.get("doi") or item.get("id"),
                f"authors={', '.join(authors[:3])}; venue={source.get('display_name', '')}; cited_by={item.get('cited_by_count', 0)}",
                item.get("publication_date"),
                "openalex",
                args.query,
                "OpenAlex works search",
                {
                    "authors": authors,
                    "venue": source.get("display_name"),
                    "doi": item.get("doi"),
                    "openalex_id": item.get("id"),
                    "citation_count": item.get("cited_by_count"),
                    "abstract": clean_text(abstract, 1800),
                    "open_access": (item.get("open_access") or {}).get("is_oa"),
                    "pdf_url": best_location.get("pdf_url") if isinstance(best_location, dict) else None,
                    "oa_landing_page": best_location.get("landing_page_url") if isinstance(best_location, dict) else None,
                    "oa_repository": best_source.get("display_name"),
                    "retrieval_stage": "discovery",
                },
            )
        )
    return results


def search_crossref(args: argparse.Namespace) -> list[dict[str, object]]:
    offset = (args.page - 1) * args.limit
    params = {"query": args.query, "rows": args.limit}
    params.update({"cursor": args.cursor} if args.cursor else {"offset": offset})
    filters = [f"{key}:{value}" for key, value in
               (("from-pub-date", args.from_date), ("until-pub-date", args.until_date)) if value]
    if filters:
        params["filter"] = ",".join(filters)
    data = request_json(
        "https://api.crossref.org/works",
        params,
        args.timeout,
    )
    message = data["message"]
    args.search_metadata = {"count": message["total-results"], "page": args.page,
                            "per_page": args.limit, "offset": offset}
    if args.cursor:
        args.search_metadata.update(cursor=args.cursor, next_cursor=message.get("next-cursor"),
                                    has_more=bool(message["items"] and message.get("next-cursor")))
    else:
        args.search_metadata.update(has_more=offset + len(message["items"]) < message["total-results"])
        args.search_metadata["next_page"] = args.page + 1 if args.search_metadata["has_more"] else None
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
                {
                    "authors": [
                        " ".join(part for part in (author.get("given"), author.get("family")) if part)
                        for author in item.get("author", [])[:12]
                    ],
                    "venue": (item.get("container-title") or [""])[0],
                    "doi": item.get("DOI"),
                    "abstract": clean_text(item.get("abstract") or "", 1800),
                    "type": item.get("type"),
                    "retrieval_stage": "discovery",
                },
            )
        )
    return results


def search_semantic_scholar(args: argparse.Namespace) -> list[dict[str, object]]:
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    endpoint = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": args.query, "offset": args.offset if args.offset is not None else (args.page - 1) * args.limit,
        "limit": args.limit,
        "fields": "title,url,authors,year,venue,abstract,citationCount,externalIds,openAccessPdf",
    }
    if args.paper_id:
        endpoint = f"https://api.semanticscholar.org/graph/v1/paper/{quote(args.paper_id, safe='')}/{args.relation}"
        del params["query"]
    elif args.bulk:
        endpoint += "/bulk"
        del params["offset"]
        del params["limit"]
        if args.token:
            params["token"] = args.token
    if not args.paper_id and (args.from_date or args.until_date):
        params["year"] = f"{(args.from_date or '')[:4]}-{(args.until_date or '')[:4]}"
    data = request_json(endpoint, params, args.timeout, headers={"x-api-key": api_key} if api_key else None)
    args.search_metadata = {"page": args.page, "per_page": args.limit}
    for field, output in (("total", "count"), ("offset", "offset"), ("next", "next_offset")):
        if field in data:
            args.search_metadata[output] = data[field]
    if args.bulk and not args.paper_id:
        args.search_metadata.update(next_token=data.get("token"), token=args.token,
                                    count_is_estimate=True, has_more=bool(data.get("token")))
    else:
        args.search_metadata["has_more"] = data.get("next") is not None
    papers = data["data"]
    if papers is None:
        raise SearchError("Semantic Scholar did not expose the requested records; missing data is not an empty reference list")
    if args.paper_id:
        field = "citedPaper" if args.relation == "references" else "citingPaper"
        papers = [item[field] for item in papers]
    args.search_metadata["returned"] = len(papers)
    if args.bulk and not args.paper_id:
        args.search_metadata.update(per_page=len(papers), requested_limit=args.limit)
    return [
        record(
            item.get("title"), item.get("url"), item.get("abstract"),
            str(item["year"]) if item.get("year") is not None else None,
            "semantic-scholar", args.query,
            f"Semantic Scholar {args.relation} for {args.paper_id}" if args.paper_id else "Semantic Scholar relevance search",
            {
                "paper_id": item.get("paperId"),
                "authors": [author["name"] for author in item.get("authors", [])],
                "venue": item.get("venue"), "doi": (item.get("externalIds") or {}).get("DOI"),
                "arxiv_id": (item.get("externalIds") or {}).get("ArXiv"),
                "external_ids": item.get("externalIds") or {},
                "citation_count": item.get("citationCount"),
                "abstract": clean_text(item.get("abstract"), 1800),
                "pdf_url": (item.get("openAccessPdf") or {}).get("url"),
                "retrieval_stage": "discovery",
            },
        )
        for item in papers
    ]


def search_pubmed(args: argparse.Namespace) -> list[dict[str, object]]:
    endpoint = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    common = {"db": "pubmed", "tool": "research-router"}
    api_key = os.environ.get("NCBI_API_KEY")
    if api_key:
        common["api_key"] = api_key
    data = request_json(
        f"{endpoint}/esearch.fcgi",
        {**common, "term": args.query, "retmode": "json", "retmax": args.limit, "retstart": (args.page - 1) * args.limit,
         **({"datetype": "pdat", "mindate": args.from_date or "1900/01/01",
             "maxdate": args.until_date or datetime.now(timezone.utc).date().isoformat()}
            if args.from_date or args.until_date else {})},
        args.timeout,
    )["esearchresult"]
    args.search_metadata = {
        "count": int(data["count"]), "page": args.page,
        "per_page": int(data["retmax"]), "offset": int(data["retstart"]),
    }
    args.search_metadata["has_more"] = int(data["retstart"]) + len(data["idlist"]) < int(data["count"])
    args.search_metadata["next_page"] = args.page + 1 if args.search_metadata["has_more"] else None
    if not data["idlist"]:
        return []
    payload = request_bytes(
        f"{endpoint}/efetch.fcgi",
        {**common, "id": ",".join(data["idlist"]), "retmode": "xml"},
        args.timeout, accept="application/xml",
    )
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise SearchError("PubMed did not return valid XML") from exc
    error = root.findtext("ERROR")
    if error:
        raise SearchError(error)
    results = []
    for entry in root:
        def text(path: str) -> str:
            node = entry.find(path)
            return "".join(node.itertext()) if node is not None else ""

        pmid = text(".//PMID")
        abstract = "\n".join("".join(node.itertext()) for node in entry.findall(".//Abstract/AbstractText"))
        authors = [
            " ".join(part for part in (author.findtext("ForeName"), author.findtext("LastName")) if part)
            or author.findtext("CollectiveName", "")
            for author in entry.findall(".//AuthorList/Author")
        ]
        pmc = text("./*/ArticleIdList/ArticleId[@IdType='pmc']")
        results.append(record(
            text(".//ArticleTitle"), f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", abstract,
            text(".//PubDate/Year") or text(".//PubDate/MedlineDate"), "pubmed", args.query,
            "PubMed ESearch and selected-record EFetch",
            {
                "pmid": pmid, "authors": authors, "venue": text(".//Journal/Title"),
                "doi": text("./*/ArticleIdList/ArticleId[@IdType='doi']"),
                "abstract": clean_text(abstract, 1800),
                "pmc_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmc}/" if pmc else None,
                "retrieval_stage": "discovery",
            },
        ))
    return results


def search_serpapi_scholar(args: argparse.Namespace) -> list[dict[str, object]]:
    api_key = os.environ.get("SERPAPI_API_KEY")
    if not api_key:
        raise SearchError("serpapi-scholar requires SERPAPI_API_KEY in the process environment")
    data = request_json(
        "https://serpapi.com/search.json",
        {"engine": "google_scholar", "q": args.query, "num": args.limit,
         "start": (args.page - 1) * args.limit, "hl": args.language, "api_key": api_key,
         **({"as_ylo": args.from_date[:4]} if args.from_date else {}),
         **({"as_yhi": args.until_date[:4]} if args.until_date else {})},
        args.timeout,
    )
    if data.get("error"):
        raise SearchError(f"SerpApi: {data['error']}")
    args.search_metadata = {
        "count": data.get("search_information", {}).get("total_results"),
        "count_is_estimate": True, "page": args.page, "per_page": args.limit,
    }
    args.search_metadata["next_page"] = args.page + 1 if data.get("serpapi_pagination", {}).get("next") else None
    args.search_metadata["has_more"] = args.search_metadata["next_page"] is not None
    results = []
    for item in data.get("organic_results", [])[: args.limit]:
        publication = item.get("publication_info", {})
        links = item.get("inline_links", {})
        snippet = item.get("snippet", "")
        results.append(record(
            item.get("title"), item.get("link"), snippet, _scholar_year(publication.get("summary", "")),
            "serpapi-scholar", args.query, "SerpApi Google Scholar discovery; snippet only",
            {
                "authors": [author["name"] for author in publication.get("authors", [])],
                "publication_info": publication.get("summary"),
                "citation_count": links.get("cited_by", {}).get("total"),
                "citing_url": links.get("cited_by", {}).get("link"),
                "version_count": links.get("versions", {}).get("total"),
                "versions_url": links.get("versions", {}).get("link"),
                "pdf_url": next((resource["link"] for resource in item.get("resources", []) if resource.get("file_format") == "PDF"), None),
                "abstract_status": "snippet-only" if snippet else "missing",
                "retrieval_stage": "discovery",
            },
        ))
    return results


def search_arxiv(args: argparse.Namespace) -> list[dict[str, object]]:
    query = args.query if re.search(r"\b(?:all|ti|au|abs|cat|id|submittedDate|lastUpdatedDate):", args.query) else f"all:{args.query}"
    if args.from_date or args.until_date:
        start_date = (args.from_date or "1991-01-01").replace("-", "") + "0000"
        end_date = (args.until_date or datetime.now(timezone.utc).date().isoformat()).replace("-", "") + "2359"
        query = f"({query}) AND submittedDate:[{start_date} TO {end_date}]"
    offset = (args.page - 1) * args.limit
    payload = request_bytes(
        "https://export.arxiv.org/api/query",
        {"search_query": query, "start": offset, "max_results": args.limit,
         "sortBy": "submittedDate", "sortOrder": "descending"},
        args.timeout,
        accept="application/atom+xml",
    )
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise SearchError("arXiv endpoint did not return valid Atom XML") from exc
    total = int(root.findtext("{http://a9.com/-/spec/opensearch/1.1/}totalResults", "0"))
    args.search_metadata = {"count": total, "page": args.page, "per_page": args.limit,
                            "offset": offset, "has_more": offset + args.limit < total,
                            "next_page": args.page + 1 if offset + args.limit < total else None,
                            "date_field": "submittedDate", "source_query": query}
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
                {
                    "authors": [
                        child_node.text.strip()
                        for child_node in entry.findall("{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name")
                        if child_node.text
                    ],
                    "arxiv_id": child("id").rsplit("/", 1)[-1],
                    "updated_at": child("updated"),
                    "doi": entry.findtext("{http://arxiv.org/schemas/atom}doi"),
                    "pdf_url": child("id").replace("/abs/", "/pdf/"),
                    "html_url": "https://arxiv.org/html/" + child("id").rsplit("/", 1)[-1],
                    "categories": [node.attrib.get("term") for node in entry.findall("{http://www.w3.org/2005/Atom}category")],
                    "retrieval_stage": "discovery",
                },
            )
        )
    return results


def search_dblp(args: argparse.Namespace) -> list[dict[str, object]]:
    offset = (args.page - 1) * args.limit
    if args.venue_url:
        xml_url = args.venue_url.removesuffix(".html") + ".xml"
        try:
            root = ET.fromstring(request_bytes(xml_url, None, args.timeout, accept="application/xml"))
        except ET.ParseError as exc:
            raise SearchError("DBLP conference directory did not return XML; access challenges are not paper records") from exc
        papers = root.findall(".//inproceedings")
        args.search_metadata = {"count": len(papers), "page": args.page, "per_page": args.limit,
                                "offset": offset, "directory": args.venue_url,
                                "has_more": offset + args.limit < len(papers),
                                "next_page": args.page + 1 if offset + args.limit < len(papers) else None}
        return [record("".join(p.find("title").itertext()), "https://dblp.org/rec/" + p.attrib["key"],
                       p.findtext("booktitle"), p.findtext("year"), "dblp", args.query,
                       "DBLP conference directory enumeration", {"authors": [a.text for a in p.findall("author")],
                       "venue": p.findtext("booktitle"), "dblp_key": p.attrib["key"],
                       "official_page": p.findtext("ee"), "doi": p.findtext("doi"), "retrieval_stage": "discovery"})
                for p in papers[offset:offset + args.limit]]
    data = request_json("https://dblp.org/search/publ/api",
                        {"q": args.query, "h": args.limit, "f": offset, "format": "json"}, args.timeout)
    hits = data["result"]["hits"]
    total = int(hits["@total"])
    args.search_metadata = {"count": total, "page": args.page, "per_page": args.limit,
                            "offset": offset, "has_more": offset + args.limit < total,
                            "next_page": args.page + 1 if offset + args.limit < total else None,
                            "date_precision": "year", "date_filter": "query expression"}
    rows = hits.get("hit", [])
    if isinstance(rows, dict):
        rows = [rows]
    results = []
    for row in rows:
        item = row["info"]
        authors = (item.get("authors") or {}).get("author", [])
        if isinstance(authors, dict):
            authors = [authors]
        results.append(record(item.get("title"), item.get("url"), item.get("venue"), item.get("year"),
                              "dblp", args.query, "DBLP publication search", {
                              "authors": [a["text"] if isinstance(a, dict) else a for a in authors],
                              "venue": item.get("venue"), "doi": item.get("doi"),
                              "dblp_key": item.get("key"), "official_page": item.get("ee"),
                              "type": item.get("type"), "retrieval_stage": "discovery"}))
    return results


class GoogleScholarParser(HTMLParser):
    """Parse the bounded, public result markup used by Google Scholar."""

    VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, object]] = []
        self.current: dict[str, object] | None = None
        self.result_depth: int | None = None
        self.tag_stack: list[str] = []
        self.capture: dict[str, object] | None = None
        self.fl_depth: int | None = None
        self.fl_link: dict[str, object] | None = None
        self.pdf_depth: int | None = None

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        values = dict(attrs)
        return set((values.get("class") or "").split())

    def _begin_capture(self, kind: str, tag: str, depth: int) -> None:
        self.capture = {"kind": kind, "tag": tag, "depth": depth, "parts": []}

    def _finish_capture(self) -> None:
        if self.capture is None or self.current is None:
            return
        parts = self.capture["parts"]
        value = clean_text(" ".join(parts if isinstance(parts, list) else []), 1200)
        self.current[str(self.capture["kind"])] = value
        self.capture = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        depth = len(self.tag_stack)
        values = dict(attrs)
        classes = self._classes(attrs)
        if tag == "div" and "gs_ri" in classes:
            self.current = {
                "title": "",
                "url": "",
                "authors_line": "",
                "snippet": "",
                "pdf_url": "",
                "fl_links": [],
            }
            self.result_depth = depth
        elif self.current is not None:
            if tag == "h3" and "gs_rt" in classes:
                self._begin_capture("title", tag, depth)
            elif tag == "div" and "gs_a" in classes:
                self._begin_capture("authors_line", tag, depth)
            elif tag == "div" and "gs_rs" in classes:
                self._begin_capture("snippet", tag, depth)
            elif tag == "div" and "gs_fl" in classes:
                self.fl_depth = depth
            elif tag == "div" and "gs_ggs" in classes:
                self.pdf_depth = depth
            elif tag == "a":
                href = values.get("href") or ""
                if self.pdf_depth is not None and depth > self.pdf_depth:
                    if not self.current.get("pdf_url"):
                        self.current["pdf_url"] = href
                if self.fl_depth is not None and depth > self.fl_depth:
                    self.fl_link = {"depth": depth, "href": href, "parts": []}
                elif self.capture is not None and self.capture.get("kind") == "title":
                    self.current["url"] = href
        if tag not in self.VOID_TAGS:
            self.tag_stack.append(tag)

    def handle_data(self, data: str) -> None:
        if self.capture is not None:
            parts = self.capture["parts"]
            if isinstance(parts, list):
                parts.append(data)
        if self.fl_link is not None:
            parts = self.fl_link["parts"]
            if isinstance(parts, list):
                parts.append(data)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.tag_stack:
            return
        depth = len(self.tag_stack) - 1
        if self.capture is not None:
            if self.capture.get("depth") == depth and self.capture.get("tag") == tag:
                self._finish_capture()
        if self.fl_link is not None:
            if self.fl_link.get("depth") == depth and tag == "a":
                parts = self.fl_link["parts"]
                text = clean_text(" ".join(parts if isinstance(parts, list) else []), 240)
                links = self.current.get("fl_links", []) if self.current else []
                if isinstance(links, list):
                    links.append({"href": self.fl_link.get("href", ""), "text": text})
                self.fl_link = None
        if tag == "div" and self.current is not None:
            if self.fl_depth == depth:
                self.fl_depth = None
            if self.pdf_depth == depth:
                self.pdf_depth = None
            if self.result_depth == depth:
                self.results.append(self.current)
                self.current = None
                self.result_depth = None
                self.capture = None
                self.fl_link = None
                self.fl_depth = None
                self.pdf_depth = None
        self.tag_stack.pop()


def _scholar_year(authors_line: str) -> str | None:
    years = re.findall(r"\b(?:19|20)\d{2}\b", authors_line)
    return years[-1] if years else None


def _scholar_authors(authors_line: str) -> list[str]:
    author_text = re.split(r"\s*[-–—]\s*", authors_line, maxsplit=1)[0]
    author_text = re.sub(r"[\s.…�]+$", "", author_text).strip()
    if not author_text:
        return []
    return [item.strip() for item in author_text.split(",") if item.strip()]


def _scholar_link_counts(item: dict[str, object]) -> tuple[int | None, int | None]:
    citation_count: int | None = None
    version_count: int | None = None
    links = item.get("fl_links", [])
    if not isinstance(links, list):
        return citation_count, version_count
    for link in links:
        if not isinstance(link, dict):
            continue
        text = clean_text(link.get("text"), 240).lower()
        match = re.search(r"cited by\s+(\d+)", text)
        if match:
            citation_count = int(match.group(1))
        match = re.search(r"(?:all\s+)?(\d+)\s+versions?", text)
        if match:
            version_count = int(match.group(1))
    return citation_count, version_count


def search_google_scholar(args: argparse.Namespace) -> list[dict[str, object]]:
    endpoint = "https://scholar.google.com/scholar"
    params = {"q": args.query, "start": (args.page - 1) * 10,
              "num": 10, "hl": args.language, "as_sdt": "0,5"}
    if args.from_date:
        params["as_ylo"] = args.from_date[:4]
    if args.until_date:
        params["as_yhi"] = args.until_date[:4]
    payload = request_bytes(
        endpoint,
        params,
        args.timeout,
        accept="text/html,application/xhtml+xml",
    )
    document = payload.decode("utf-8", errors="replace")
    lowered = document.lower()
    challenge_markers = (
        "captcha",
        "recaptcha",
        "unusual traffic",
        "/sorry/",
        "before you continue to google",
    )
    if any(marker in lowered for marker in challenge_markers):
        raise SearchError(
            "Google Scholar returned a CAPTCHA, rate-limit, or challenge page; stop without retries"
        )
    parser = GoogleScholarParser()
    parser.feed(document)
    parser.close()
    args.search_metadata = {"page": args.page, "per_page": 10, "requested_limit": args.limit,
                            "returned": len(parser.results), "offset": (args.page - 1) * 10,
                            "next_page": args.page + 1 if parser.results else None,
                            "has_more": None, "date_precision": "year",
                            "paging_note": "Next page is a continuation candidate, not a confirmed remaining total; the complete returned page is retained."}
    results: list[dict[str, object]] = []
    for item in parser.results:
        authors_line = str(item.get("authors_line") or "")
        title = str(item.get("title") or "")
        snippet = str(item.get("snippet") or "")
        citation_count, version_count = _scholar_link_counts(item)
        pdf_url = str(item.get("pdf_url") or "")
        results.append(
            record(
                title,
                urljoin(endpoint, str(item.get("url") or "")),
                snippet,
                _scholar_year(authors_line),
                "google-scholar",
                args.query,
                "Google Scholar public HTML discovery; abstract snippet only",
                {
                    "authors": _scholar_authors(authors_line),
                    "citation_count": citation_count,
                    "version_count": version_count,
                    "pdf_url": urljoin(endpoint, pdf_url) if pdf_url else None,
                    "abstract_status": "snippet-only" if snippet else "missing",
                    "retrieval_stage": "discovery",
                },
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
    "semantic-scholar": search_semantic_scholar,
    "pubmed": search_pubmed,
    "serpapi-scholar": search_serpapi_scholar,
    "crossref": search_crossref,
    "arxiv": search_arxiv,
    "dblp": search_dblp,
    "google-scholar": search_google_scholar,
    "discourse": search_discourse,
    "rss": search_rss,
    "ddgs": search_ddgs,
}


LIMITS = {
    "github": ["Unauthenticated GitHub Search API requests are rate limited."],
    "stackoverflow": ["Respect Stack Exchange quota, backoff, and API policies."],
    "openalex": [
        "OPENALEX_API_KEY is optional; API budgets and rate limits apply.",
        "This response contains one page; search_metadata.count is the source-reported total matching this query, not the size of the research field.",
    ],
    "semantic-scholar": [
        "SEMANTIC_SCHOLAR_API_KEY is optional; anonymous requests share a rate-limit pool.",
        "Relevance search exposes at most 1,000 ranked matches; references and citations use separate paginated endpoints.",
        "Abstracts can be missing; citation links and counts do not replace primary-paper evidence.",
    ],
    "pubmed": ["NCBI_API_KEY is optional; E-utilities rate limits apply.", "Retrieved metadata and abstracts do not establish that the full paper was read."],
    "serpapi-scholar": ["Requires SERPAPI_API_KEY and uses that account's search allowance only when selected.", "Google Scholar totals are estimates and result snippets are not full abstracts or full text."],
    "arxiv": ["Use a polite request interval; the endpoint is for discovery metadata."],
    "dblp": ["DBLP indexes bibliography, not abstracts or full text; h/f paginate search hits.", "Conference enumeration requires the selected DBLP directory's public XML; stop on access challenges."],
    "google-scholar": [
        "Public HTML discovery only; result snippets are not guaranteed to be complete abstracts.",
        "Use a low request rate and stop on 403, 429, CAPTCHA, or challenge pages; do not retry aggressively.",
        "Enrich selected records with OpenAlex, arXiv, Crossref, or the publisher before paper-brief or full evidence.",
    ],
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
    parser.add_argument("--from-date", help="Academic publication start date, YYYY-MM-DD")
    parser.add_argument("--until-date", help="Academic publication cutoff date, YYYY-MM-DD")
    parser.add_argument("--cursor", help="OpenAlex/Crossref cursor; use * for the first cursor request")
    parser.add_argument("--bulk", action="store_true", help="Semantic Scholar bulk retrieval (retains the whole server batch)")
    parser.add_argument("--token", help="Semantic Scholar bulk continuation token")
    parser.add_argument("--offset", type=int, help="Exact Semantic Scholar next_offset")
    parser.add_argument("--venue-url", help="DBLP conference volume HTML URL for complete directory enumeration")
    parser.add_argument("--language", default="en")
    parser.add_argument("--paper-id", help="Semantic Scholar, DOI:, ARXIV:, or PMID: ID for citation-chain discovery")
    parser.add_argument("--relation", choices=["references", "citations"], default="references", help="Semantic Scholar relation used with --paper-id")
    args = parser.parse_args()
    args.search_metadata = None
    max_limit = {"openalex": 100, "semantic-scholar": 100, "serpapi-scholar": 20, "dblp": 1000}.get(args.provider, 50)
    if args.provider == "semantic-scholar" and args.paper_id:
        max_limit = 1000
    if not 1 <= args.limit <= max_limit:
        parser.error(f"--limit must be between 1 and {max_limit}")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.page < 1:
        parser.error("--page must be positive")
    if args.provider == "google-scholar" and args.limit > 10:
        parser.error("--limit must be between 1 and 10 for google-scholar")
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
                **({"search_metadata": args.search_metadata} if args.search_metadata is not None else {}),
                "results": results,
                "evidence_level": "discovery",
                "next_action": "continue_discovery" if args.provider in {"openalex", "crossref", "arxiv", "semantic-scholar", "dblp", "google-scholar"} and args.search_metadata and
                    (args.search_metadata.get("has_more") or args.search_metadata.get("next_page")) else "read_selected",
                **({"search_scope": {"from_date": args.from_date, "until_date": args.until_date,
                                     "language": args.language, "retrieved_at": datetime.now(timezone.utc).isoformat()}}
                   if args.provider in {"openalex", "crossref", "arxiv", "semantic-scholar", "dblp", "google-scholar", "pubmed", "serpapi-scholar"} else {}),
                "limits": LIMITS.get(args.provider, []),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
