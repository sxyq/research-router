#!/usr/bin/env python3
"""Read public GitHub repositories with unauthenticated REST API requests."""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


API = "https://api.github.com"
USER_AGENT = "research-router/github-public"
TIMEOUT = 20.0
MAX_RESPONSE_BYTES = 8_000_000
MAX_FILE_CHARS = 40_000


class GitHubError(RuntimeError):
    pass


def request_json(path: str, params: dict[str, object] | None = None) -> Any:
    url = f"{API}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        if exc.code == 403 and exc.headers.get("X-RateLimit-Remaining") == "0":
            raise GitHubError("GitHub unauthenticated API rate limit reached; try again later") from exc
        raise GitHubError(f"GitHub API HTTP {exc.code} for {url}") from exc
    except (URLError, TimeoutError) as exc:
        raise GitHubError(f"GitHub API request failed for {url}: {exc}") from exc
    if len(payload) > MAX_RESPONSE_BYTES:
        raise GitHubError(f"GitHub API response exceeded {MAX_RESPONSE_BYTES} bytes")
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GitHubError(f"GitHub API returned invalid JSON for {url}") from exc


def repository_slug(value: str) -> str:
    pieces = value.strip().strip("/").split("/")
    if len(pieces) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in pieces):
        raise ValueError("repository must be owner/name")
    if any(part in {".", ".."} for part in pieces):
        raise ValueError("repository must be owner/name")
    return "/".join(pieces)


def _repo_path(repo: str, suffix: str = "") -> str:
    slug = repository_slug(repo)
    encoded = "/".join(quote(part, safe="") for part in slug.split("/"))
    return f"/repos/{encoded}{suffix}"


def _decode_file(data: Any) -> str:
    if not isinstance(data, dict):
        raise GitHubError("GitHub contents endpoint returned an unexpected response")
    if data.get("encoding") != "base64" or not isinstance(data.get("content"), str):
        raise GitHubError("GitHub did not return a base64 file payload")
    try:
        raw = base64.b64decode(data["content"], validate=False)
    except (ValueError, TypeError) as exc:
        raise GitHubError("GitHub returned invalid base64 file content") from exc
    text = raw.decode("utf-8", errors="replace")
    truncated = len(text) > MAX_FILE_CHARS
    return text[:MAX_FILE_CHARS] + ("\n...[truncated]" if truncated else "")


def search(query: str, limit: int = 5) -> dict[str, Any]:
    data = request_json("/search/repositories", {"q": query, "per_page": limit})
    results = []
    for item in data.get("items", [])[:limit] if isinstance(data, dict) else []:
        results.append(
            {
                "repository": item.get("full_name"),
                "title": item.get("full_name") or item.get("name"),
                "url": item.get("html_url"),
                "excerpt": item.get("description") or "",
                "published_at": item.get("updated_at"),
                "stars": item.get("stargazers_count"),
                "language": item.get("language"),
                "license": (item.get("license") or {}).get("spdx_id"),
                "source": "github-rest-api",
                "evidence_level": "discovery",
            }
        )
    return {"mode": "search", "query": query, "results": results}


def repository(repo: str) -> dict[str, Any]:
    slug = repository_slug(repo)
    data = request_json(_repo_path(slug))
    if not isinstance(data, dict):
        raise GitHubError("GitHub repository endpoint returned an unexpected response")
    readme = None
    try:
        readme_data = request_json(_repo_path(slug, "/readme"))
        readme = _decode_file(readme_data)
    except GitHubError:
        readme = None
    return {
        "mode": "repo",
        "repository": slug,
        "url": data.get("html_url"),
        "description": data.get("description"),
        "default_branch": data.get("default_branch"),
        "language": data.get("language"),
        "license": (data.get("license") or {}).get("spdx_id"),
        "stars": data.get("stargazers_count"),
        "forks": data.get("forks_count"),
        "open_issues": data.get("open_issues_count"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "pushed_at": data.get("pushed_at"),
        "archived": data.get("archived"),
        "readme": readme,
        "readme_url": f"https://github.com/{slug}#readme" if readme is not None else None,
        "source": "github-rest-api",
        "evidence_level": "detail" if readme is not None else "partial",
    }


def tree(repo: str, limit: int = 5000) -> dict[str, Any]:
    slug = repository_slug(repo)
    metadata = request_json(_repo_path(slug))
    branch = metadata.get("default_branch") if isinstance(metadata, dict) else None
    if not isinstance(branch, str) or not branch:
        raise GitHubError("GitHub repository has no reported default branch")
    data = request_json(_repo_path(slug, f"/git/trees/{quote(branch, safe='')}"), {"recursive": 1})
    if not isinstance(data, dict):
        raise GitHubError("GitHub tree endpoint returned an unexpected response")
    entries = data.get("tree", [])
    items = [
        {"path": item.get("path"), "type": item.get("type"), "size": item.get("size"), "sha": item.get("sha")}
        for item in entries[:limit]
        if isinstance(item, dict)
    ]
    return {
        "mode": "tree",
        "repository": slug,
        "default_branch": branch,
        "truncated": bool(data.get("truncated")) or len(entries) > limit,
        "count": len(items),
        "results": items,
        "source": "github-rest-api",
        "evidence_level": "detail",
    }


def file(repo: str, path: str, ref: str | None = None) -> dict[str, Any]:
    slug = repository_slug(repo)
    clean_path = path.strip().strip("/")
    if not clean_path or any(part in {".", ".."} for part in clean_path.split("/")):
        raise ValueError("path must be a repository-relative file path")
    suffix = "/contents/" + quote(clean_path, safe="/")
    params = {"ref": ref} if ref else None
    data = request_json(_repo_path(slug, suffix), params)
    text = _decode_file(data)
    return {
        "mode": "file",
        "repository": slug,
        "path": clean_path,
        "ref": ref,
        "url": data.get("html_url") if isinstance(data, dict) else None,
        "content": text,
        "size": data.get("size") if isinstance(data, dict) else None,
        "source": "github-rest-api",
        "evidence_level": "detail",
    }


def collection(repo: str, mode: str, limit: int = 10) -> dict[str, Any]:
    slug = repository_slug(repo)
    if mode == "issues":
        data = request_json(_repo_path(slug, "/issues"), {"state": "all", "per_page": limit, "sort": "updated"})
        items = [item for item in data if isinstance(item, dict) and "pull_request" not in item]
        results = [
            {
                "number": item.get("number"),
                "title": item.get("title"),
                "state": item.get("state"),
                "url": item.get("html_url"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "comments": item.get("comments"),
                "labels": [label.get("name") for label in item.get("labels", []) if isinstance(label, dict)],
                "excerpt": item.get("body") or "",
            }
            for item in items[:limit]
        ]
    elif mode == "releases":
        data = request_json(_repo_path(slug, "/releases"), {"per_page": limit})
        results = [
            {
                "tag": item.get("tag_name"),
                "title": item.get("name") or item.get("tag_name"),
                "url": item.get("html_url"),
                "published_at": item.get("published_at"),
                "prerelease": item.get("prerelease"),
                "excerpt": item.get("body") or "",
            }
            for item in data[:limit]
            if isinstance(item, dict)
        ]
    else:
        data = request_json(_repo_path(slug, "/commits"), {"per_page": limit})
        results = [
            {
                "sha": str(item.get("sha") or "")[:12],
                "title": ((item.get("commit") or {}).get("message") or "").splitlines()[0],
                "url": item.get("html_url"),
                "published_at": ((item.get("commit") or {}).get("committer") or {}).get("date"),
                "author": ((item.get("commit") or {}).get("author") or {}).get("name"),
            }
            for item in data[:limit]
            if isinstance(item, dict)
        ]
    return {"mode": mode, "repository": slug, "results": results, "source": "github-rest-api", "evidence_level": "detail"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)
    search_parser = subparsers.add_parser("search", help="Search public repositories")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--limit", type=int, default=5)
    for name in ("repo", "tree", "issues", "releases", "commits"):
        command = subparsers.add_parser(name)
        command.add_argument("--repo", required=True)
        command.add_argument("--limit", type=int, default=20 if name == "tree" else 10)
    file_parser = subparsers.add_parser("file", help="Read one selected public repository file")
    file_parser.add_argument("--repo", required=True)
    file_parser.add_argument("--path", required=True)
    file_parser.add_argument("--ref")
    args = parser.parse_args()
    limit = getattr(args, "limit", 1)
    if not 1 <= limit <= (5000 if args.mode == "tree" else 50):
        parser.error("limit is outside the supported range")
    try:
        if args.mode == "search":
            result = search(args.query, args.limit)
        elif args.mode == "repo":
            result = repository(args.repo)
        elif args.mode == "tree":
            result = tree(args.repo, args.limit)
        elif args.mode == "file":
            result = file(args.repo, args.path, args.ref)
        else:
            result = collection(args.repo, args.mode, args.limit)
    except (GitHubError, ValueError) as exc:
        print(json.dumps({"status": "unavailable", "mode": args.mode, "error": str(exc), "results": []}, ensure_ascii=False, indent=2))
        return 2
    has_data = bool(result.get("results", result.get("readme") or result.get("content")))
    print(json.dumps({"status": "ok" if has_data else "partial", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
