#!/usr/bin/env python3
"""Discover public GitHub repositories and retrieve selected source through bounded public paths."""

from __future__ import annotations

import argparse
import base64
import fnmatch
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


API = "https://api.github.com"
USER_AGENT = "research-router/github-public"
TIMEOUT = 20.0
MAX_RESPONSE_BYTES = 8_000_000
MAX_FILE_CHARS = 40_000
MAX_RAW_FILE_BYTES = 8_000_000
MAX_ARCHIVE_BYTES = 64_000_000
MAX_EXTRACTED_BYTES = 256_000_000
MAX_ARCHIVE_FILES = 20_000
MAX_SINGLE_FILE_BYTES = 8_000_000
MAX_GIT_REPOSITORY_KB = 512_000
SNAPSHOT_PREFIX = "research-router-github-"
API_BUDGET: dict[str, Any] = {
    "limit": None,
    "remaining": None,
    "reset_at": None,
    "authenticated": False,
}


class GitHubError(RuntimeError):
    def __init__(self, message: str, status: str = "unavailable") -> None:
        super().__init__(message)
        self.status = status


def configured_token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def api_budget() -> dict[str, Any]:
    return {**API_BUDGET, "token_configured": bool(configured_token())}


def _record_api_headers(headers: Any) -> None:
    for field, header in (("limit", "X-RateLimit-Limit"), ("remaining", "X-RateLimit-Remaining")):
        try:
            value = headers.get(header)
            if value is not None:
                API_BUDGET[field] = int(value)
        except (AttributeError, TypeError, ValueError):
            pass
    try:
        reset = headers.get("X-RateLimit-Reset")
        if reset:
            API_BUDGET["reset_at"] = datetime.fromtimestamp(int(reset), timezone.utc).isoformat()
    except (AttributeError, TypeError, ValueError, OSError):
        pass


def request_json(path: str, params: dict[str, object] | None = None) -> Any:
    url = f"{API}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = configured_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            _record_api_headers(response.headers)
            API_BUDGET["authenticated"] = bool(token)
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        _record_api_headers(exc.headers)
        if exc.headers.get("X-RateLimit-Remaining") is not None:
            API_BUDGET["authenticated"] = bool(token)
        if exc.code == 429 or exc.headers.get("X-RateLimit-Remaining") == "0":
            raise GitHubError("GitHub REST rate limit reached", "rate-limited") from exc
        if exc.code == 403:
            try:
                detail = exc.read(2048).decode("utf-8", errors="replace").lower()
            except (AttributeError, OSError):
                detail = ""
            if "rate limit" in detail or "secondary rate limit" in detail:
                raise GitHubError("GitHub REST search or secondary rate limit reached", "rate-limited") from exc
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
    slug = value.strip()
    if slug.startswith("/") or slug.endswith("/"):
        raise ValueError("repository must be owner/name")
    pieces = slug.split("/")
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


def _safe_repo_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        raise ValueError("path must be a repository-relative file path")
    raw_path = value.strip()
    if raw_path.startswith("/") or raw_path.endswith("/"):
        raise ValueError("path must be a repository-relative file path")
    parts = raw_path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("path must be a repository-relative file path")
    return "/".join(parts)


def _safe_ref(value: str) -> str:
    if not isinstance(value, str) or not value or not re.fullmatch(r"[A-Za-z0-9._/-]+", value):
        raise ValueError("ref contains unsupported characters")
    if any(part in {"", ".", ".."} for part in value.split("/")) or value.startswith("-"):
        raise ValueError("ref is not a valid branch, tag, or commit")
    return value


def raw_file(repo: str, path: str, ref: str) -> dict[str, Any] | None:
    slug = repository_slug(repo)
    clean_path = _safe_repo_path(path)
    clean_ref = _safe_ref(ref)
    encoded_ref = quote(clean_ref, safe="/")
    encoded_path = quote(clean_path, safe="/")
    url = f"https://raw.githubusercontent.com/{slug}/{encoded_ref}/{encoded_path}"
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/plain,application/octet-stream"})
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            final_host = urlparse(response.geturl()).hostname if hasattr(response, "geturl") else "raw.githubusercontent.com"
            if final_host != "raw.githubusercontent.com":
                raise GitHubError("raw file request redirected outside the GitHub raw host")
            payload = response.read(MAX_RAW_FILE_BYTES + 1)
    except HTTPError as exc:
        if exc.code == 404:
            return None
        if exc.code == 429 or exc.headers.get("X-RateLimit-Remaining") == "0":
            raise GitHubError("GitHub raw content is rate-limited", "rate-limited") from exc
        raise GitHubError(f"GitHub raw content HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise GitHubError(f"GitHub raw content request failed: {exc}") from exc
    if len(payload) > MAX_RAW_FILE_BYTES:
        raise GitHubError(f"GitHub raw file exceeds {MAX_RAW_FILE_BYTES} bytes")
    content = payload.decode("utf-8", errors="replace")
    truncated = len(content) > MAX_FILE_CHARS
    return {
        "mode": "file",
        "repository": slug,
        "path": clean_path,
        "ref": clean_ref,
        "url": f"https://github.com/{slug}/blob/{encoded_ref}/{encoded_path}",
        "content": content[:MAX_FILE_CHARS] + ("\n...[truncated]" if truncated else ""),
        "size": len(payload),
        "source": "github-raw",
        "retrieval_method": "raw",
        "evidence_level": "detail",
    }


def _git_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("GITHUB_TOKEN", None)
    env.pop("GH_TOKEN", None)
    env.update({
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GCM_INTERACTIVE": "Never",
    })
    return env


def _run_git(args: list[str], *, cwd: Path | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-c", "credential.helper=", *args],
            cwd=cwd,
            env=_git_environment(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitHubError(f"Git command failed: {exc}") from exc


def _git_snapshot(slug: str, ref: str | None, root: Path) -> dict[str, Any]:
    if shutil.which("git") is None:
        raise GitHubError("git executable is not installed")
    url = f"https://github.com/{slug}.git"
    command = ["clone", "--depth=1", "--filter=blob:limit=8388608", "--single-branch", "--no-checkout"]
    if ref and not re.fullmatch(r"[0-9a-fA-F]{7,40}", ref):
        command.extend(["--branch", ref])
    command.extend([url, str(root)])
    try:
        cloned = _run_git(command)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitHubError(f"shallow Git clone failed: {exc}") from exc
    if cloned.returncode != 0:
        raise GitHubError("shallow Git clone failed: " + cloned.stderr.strip()[-1000:])
    if ref and re.fullmatch(r"[0-9a-fA-F]{7,40}", ref):
        fetched = _run_git(["fetch", "--depth=1", "origin", ref], cwd=root)
        if fetched.returncode != 0:
            raise GitHubError("requested Git ref could not be fetched")
        checked_out = _run_git(["checkout", "--detach", "FETCH_HEAD"], cwd=root)
        if checked_out.returncode != 0:
            raise GitHubError("requested Git ref could not be selected")
    branch_result = _run_git(["symbolic-ref", "--short", "HEAD"], cwd=root)
    commit_result = _run_git(["rev-parse", "HEAD"], cwd=root)
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None
    commit = commit_result.stdout.strip() if commit_result.returncode == 0 else None
    return {"retrieval_method": "git-shallow", "ref": ref or branch, "commit": commit}


def _download_archive(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json,application/gzip"})
    try:
        with urlopen(request, timeout=90) as response:
            final_host = urlparse(response.geturl()).hostname if hasattr(response, "geturl") else "codeload.github.com"
            if final_host not in {"codeload.github.com", "github.com"}:
                raise GitHubError("source archive request redirected outside GitHub")
            payload = response.read(MAX_ARCHIVE_BYTES + 1)
    except HTTPError as exc:
        status = "rate-limited" if exc.code == 429 or exc.headers.get("X-RateLimit-Remaining") == "0" else "unavailable"
        raise GitHubError(f"GitHub source archive HTTP {exc.code}", status) from exc
    except (URLError, TimeoutError) as exc:
        raise GitHubError(f"GitHub source archive request failed: {exc}") from exc
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise GitHubError(f"GitHub source archive exceeds {MAX_ARCHIVE_BYTES} bytes")
    return payload


def _extract_archive(payload: bytes, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        archive = tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz")
    except (tarfile.TarError, OSError) as exc:
        raise GitHubError("GitHub source archive is not a valid gzip tar") from exc
    with archive:
        try:
            members = archive.getmembers()
        except tarfile.TarError as exc:
            raise GitHubError("GitHub source archive could not be listed") from exc
        if len(members) > MAX_ARCHIVE_FILES + 10_000:
            raise GitHubError("GitHub source archive has too many entries")
        files: list[tarfile.TarInfo] = []
        total_size = 0
        roots: set[str] = set()
        for member in members:
            raw_name = member.name
            parts = raw_name.split("/")
            if member.isdir() and parts and parts[-1] == "":
                parts.pop()
            if raw_name.startswith("/") or "\\" in raw_name or not parts or any(part in {"", ".", ".."} for part in parts):
                raise GitHubError("GitHub source archive contains an unsafe root path")
            roots.add(parts[0])
            if member.isdir():
                continue
            if not member.isfile():
                raise GitHubError("GitHub source archive contains a link or special file")
            if member.size < 0 or member.size > MAX_SINGLE_FILE_BYTES:
                raise GitHubError("GitHub source archive contains an oversized file")
            total_size += member.size
            files.append(member)
            if len(files) > MAX_ARCHIVE_FILES or total_size > MAX_EXTRACTED_BYTES:
                raise GitHubError("GitHub source archive exceeds extraction limits")
        if len(roots) != 1:
            raise GitHubError("GitHub source archive has an unexpected directory layout")
        archive_root = next(iter(roots))
        extracted_root = destination / archive_root
        extracted_root.mkdir(parents=True, exist_ok=True)
        for member in members:
            parts = member.name.split("/")
            if member.isdir():
                directory = destination.joinpath(*parts)
                directory.mkdir(parents=True, exist_ok=True)
        for member in files:
            parts = member.name.split("/")
            relative = parts[1:]
            if not relative:
                raise GitHubError("GitHub source archive has a file at its root")
            target = extracted_root.joinpath(*relative)
            if not target.resolve().is_relative_to(extracted_root.resolve()):
                raise GitHubError("GitHub source archive contains an unsafe path")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise GitHubError("GitHub source archive contains duplicate file paths")
            stream = archive.extractfile(member)
            if stream is None:
                raise GitHubError("GitHub source archive contains unreadable file data")
            try:
                with stream, target.open("xb") as output:
                    shutil.copyfileobj(stream, output, length=64 * 1024)
            except (OSError, tarfile.TarError) as exc:
                raise GitHubError("GitHub source archive file data could not be read") from exc
        return extracted_root


def _archive_snapshot(slug: str, ref: str | None, snapshot_dir: Path, root: Path) -> dict[str, Any]:
    candidates: list[tuple[str, str]] = []
    if ref:
        clean_ref = _safe_ref(ref)
        if re.fullmatch(r"[0-9a-fA-F]{7,40}", clean_ref):
            candidates.append((clean_ref, f"https://codeload.github.com/{slug}/tar.gz/{quote(clean_ref, safe='')}"))
        else:
            candidates.append((clean_ref, f"https://codeload.github.com/{slug}/tar.gz/refs/heads/{quote(clean_ref, safe='/')}"))
            candidates.append((clean_ref, f"https://codeload.github.com/{slug}/tar.gz/refs/tags/{quote(clean_ref, safe='/')}"))
    else:
        branches = []
        branches.extend(branch for branch in ("main", "master") if branch not in branches)
        candidates.extend(
            (branch, f"https://codeload.github.com/{slug}/tar.gz/refs/heads/{quote(branch, safe='/')}")
            for branch in branches
        )
    errors = []
    for index, (selected_ref, url) in enumerate(candidates):
        try:
            payload = _download_archive(url)
            extract_dir = snapshot_dir / f"archive-{index}"
            extracted = _extract_archive(payload, extract_dir)
            if root.exists():
                shutil.rmtree(root)
            extracted.rename(root)
            return {"retrieval_method": "archive", "ref": selected_ref, "commit": None}
        except (GitHubError, OSError) as exc:
            errors.append(str(exc))
    raise GitHubError("source archive fallback failed: " + "; ".join(errors[-3:]))


def create_snapshot(
    repo: str,
    ref: str | None = None,
    size_kb: int | None = None,
    probe_metadata: bool = True,
) -> dict[str, Any]:
    slug = repository_slug(repo)
    clean_ref = _safe_ref(ref) if ref else None
    if size_kb is not None and size_kb < 0:
        raise ValueError("size-kb must be non-negative")
    snapshot_dir = Path(tempfile.mkdtemp(prefix=SNAPSHOT_PREFIX))
    root = snapshot_dir / "repo"
    failures: list[str] = []
    default_branch = clean_ref
    if size_kb is None and probe_metadata:
        try:
            metadata = request_json(_repo_path(slug))
            if isinstance(metadata, dict):
                size_kb = metadata.get("size") if isinstance(metadata.get("size"), int) else None
                if default_branch is None and isinstance(metadata.get("default_branch"), str):
                    default_branch = metadata["default_branch"]
        except GitHubError as exc:
            failures.append(str(exc))
    skip_git = size_kb is not None and size_kb > MAX_GIT_REPOSITORY_KB
    if skip_git:
        failures.append(f"shallow clone skipped because reported repository size exceeds {MAX_GIT_REPOSITORY_KB} KiB")
    if shutil.which("git") is not None and not skip_git:
        try:
            details = _git_snapshot(slug, clean_ref, root)
        except GitHubError as exc:
            failures.append(str(exc))
        else:
            details.update({
                "repository": slug,
                "root": str(root),
                "temporary": True,
                "status": "ok",
                "reported_size_kb": size_kb,
                "failures": failures,
            })
            (snapshot_dir / "snapshot.json").write_text(json.dumps(details), encoding="utf-8")
            return {"mode": "snapshot", **details, "api_budget": api_budget()}
    try:
        details = _archive_snapshot(slug, default_branch, snapshot_dir, root)
    except (GitHubError, ValueError, OSError) as exc:
        failures.append(str(exc))
        shutil.rmtree(snapshot_dir, ignore_errors=True)
        status = "rate-limited" if API_BUDGET.get("remaining") == 0 else "unavailable"
        raise GitHubError("all snapshot methods failed: " + "; ".join(failures), status)
    details.update({
        "repository": slug,
        "root": str(root),
        "temporary": True,
        "status": "ok",
        "reported_size_kb": size_kb,
        "failures": failures,
    })
    (snapshot_dir / "snapshot.json").write_text(json.dumps(details), encoding="utf-8")
    return {"mode": "snapshot", **details, "api_budget": api_budget()}


def _snapshot_metadata(snapshot: str) -> tuple[Path, dict[str, Any]]:
    root = Path(snapshot).expanduser().resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    snapshot_dir = root.parent
    if root.name != "repo" or snapshot_dir.parent != temp_root or not snapshot_dir.name.startswith(SNAPSHOT_PREFIX):
        raise ValueError("snapshot path was not created by this adapter")
    marker = snapshot_dir / "snapshot.json"
    try:
        details = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("snapshot metadata is missing or invalid") from exc
    if not isinstance(details, dict) or not isinstance(details.get("repository"), str):
        raise ValueError("snapshot metadata is missing the repository identity")
    recorded_root = details.get("root")
    if not isinstance(recorded_root, str) or Path(recorded_root).resolve() != root or details.get("temporary") is not True:
        raise ValueError("snapshot metadata does not match this temporary directory")
    return root, details


def _git_snapshot_tree(root: Path, limit: int) -> list[dict[str, Any]] | None:
    if not (root / ".git").is_dir() or shutil.which("git") is None:
        return None
    result = _run_git(["ls-tree", "-r", "-l", "HEAD"], cwd=root)
    if result.returncode != 0:
        raise GitHubError("could not list the local Git snapshot tree")
    entries = []
    for line in result.stdout.splitlines():
        try:
            metadata, path = line.split("\t", 1)
            fields = metadata.split()
            mode, kind, object_id = fields[:3]
            size = fields[3] if len(fields) > 3 else "-"
        except ValueError:
            continue
        entries.append({"path": path, "type": kind, "mode": mode, "size": int(size) if size.isdigit() else None})
    return entries[:limit]


def local_tree(snapshot: str, limit: int = 5000) -> dict[str, Any]:
    root, metadata = _snapshot_metadata(snapshot)
    git_entries = _git_snapshot_tree(root, limit)
    if git_entries is not None:
        result = git_entries
        count_result = _run_git(["ls-tree", "-r", "--name-only", "HEAD"], cwd=root)
        total_count = len(count_result.stdout.splitlines()) if count_result.returncode == 0 else len(result)
        method = "local-snapshot"
    else:
        entries = []
        total_size = 0
        for directory, subdirs, filenames in os.walk(root, followlinks=False):
            subdirs[:] = [name for name in subdirs if not (Path(directory) / name).is_symlink()]
            for filename in filenames:
                path = Path(directory) / filename
                if path.is_symlink() or not path.is_file():
                    continue
                size = path.stat().st_size
                total_size += size
                if total_size > MAX_EXTRACTED_BYTES:
                    raise GitHubError("snapshot exceeds the extracted-size limit")
                entries.append({"path": path.relative_to(root).as_posix(), "type": "blob", "size": size})
                if len(entries) > MAX_ARCHIVE_FILES:
                    raise GitHubError("snapshot exceeds the file-count limit")
        total_count = len(entries)
        result = entries[:limit]
        method = "local-snapshot"
    return {
        "mode": "local-tree",
        "repository": metadata["repository"],
        "root": str(root),
        "retrieval_method": method,
        "snapshot_method": metadata.get("retrieval_method"),
        "ref": metadata.get("ref"),
        "commit": metadata.get("commit"),
        "truncated": total_count > limit,
        "count": len(result),
        "total_count": total_count,
        "results": result,
        "evidence_level": "detail",
    }


def local_file(snapshot: str, path: str) -> dict[str, Any]:
    root, metadata = _snapshot_metadata(snapshot)
    clean_path = _safe_repo_path(path)
    if (root / ".git").is_dir():
        listed = _run_git(["ls-tree", "-r", "-l", "HEAD", "--", clean_path], cwd=root)
        if listed.returncode != 0 or not listed.stdout.strip():
            raise GitHubError(f"file is not present in snapshot: {clean_path}")
        object_id = None
        try:
            object_fields = listed.stdout.split("\t", 1)[0].split()
            object_id = object_fields[2]
            size = int(object_fields[3]) if len(object_fields) > 3 and object_fields[3].isdigit() else None
        except (ValueError, IndexError):
            size = None
        if object_id:
            object_size = _run_git(["cat-file", "-s", object_id], cwd=root)
            if object_size.returncode != 0:
                raise GitHubError("file was omitted from the bounded Git snapshot; use raw or REST retrieval")
            try:
                size = int(object_size.stdout.strip())
            except ValueError as exc:
                raise GitHubError("local Git snapshot returned invalid file size") from exc
        if size is not None and size > MAX_SINGLE_FILE_BYTES:
            raise GitHubError(f"file exceeds {MAX_SINGLE_FILE_BYTES} bytes")
        result = _run_git(["show", f"HEAD:{clean_path}"], cwd=root)
        if result.returncode != 0:
            raise GitHubError(f"could not read local source file: {clean_path}")
        payload = result.stdout.encode("utf-8", errors="replace")
    else:
        target = root.joinpath(*clean_path.split("/"))
        if not target.resolve().is_relative_to(root.resolve()) or target.is_symlink() or not target.is_file():
            raise GitHubError(f"file is not present in snapshot: {clean_path}")
        size = target.stat().st_size
        if size > MAX_SINGLE_FILE_BYTES:
            raise GitHubError(f"file exceeds {MAX_SINGLE_FILE_BYTES} bytes")
        payload = target.read_bytes()
    content = payload.decode("utf-8", errors="replace")
    truncated = len(content) > MAX_FILE_CHARS
    return {
        "mode": "local-file",
        "repository": metadata["repository"],
        "path": clean_path,
        "ref": metadata.get("ref"),
        "commit": metadata.get("commit"),
        "snapshot_method": metadata.get("retrieval_method"),
        "size": len(payload),
        "content": content[:MAX_FILE_CHARS] + ("\n...[truncated]" if truncated else ""),
        "source": "github-snapshot",
        "retrieval_method": "local-snapshot",
        "evidence_level": "detail",
    }


def _candidate_rank(path: str) -> tuple[int, str]:
    name = PurePosixPath(path).name.lower()
    segments = set(path.lower().split("/"))
    if name.startswith("readme"):
        rank = 0
    elif name in {"pyproject.toml", "package.json", "cargo.toml", "go.mod", "requirements.txt", "pom.xml", "build.gradle"}:
        rank = 1
    elif {".github", "workflows"}.issubset(segments) or bool({"test", "tests"} & segments):
        rank = 2
    elif any(segment in path.lower().split("/") for segment in ("src", "lib", "app")):
        rank = 3
    elif "examples" in path.lower().split("/"):
        rank = 4
    else:
        rank = 5
    return rank, path.casefold()


def local_find(snapshot: str, pattern: str, limit: int = 100) -> dict[str, Any]:
    tree_result = local_tree(snapshot, MAX_ARCHIVE_FILES)
    entries = [item for item in tree_result["results"] if fnmatch.fnmatchcase(item["path"], pattern)]
    entries.sort(key=lambda item: _candidate_rank(item["path"]))
    results = [{**item, "candidate_rank": rank + 1} for rank, item in enumerate(entries[:limit])]
    return {
        "mode": "local-find",
        "repository": tree_result["repository"],
        "root": tree_result["root"],
        "snapshot_method": tree_result.get("snapshot_method"),
        "query": pattern,
        "retrieval_method": "local-snapshot",
        "count": len(results),
        "results": results,
        "evidence_level": "detail",
    }


def cleanup_snapshot(snapshot: str) -> dict[str, Any]:
    root, metadata = _snapshot_metadata(snapshot)
    snapshot_dir = root.parent
    shutil.rmtree(snapshot_dir)
    return {"status": "ok", "mode": "cleanup", "repository": metadata["repository"], "removed": True}


def _repo_result(item: dict[str, Any], method: str) -> dict[str, Any]:
    return {
        "repository": item.get("full_name") or item.get("fullName") or item.get("repository"),
        "title": item.get("full_name") or item.get("fullName") or item.get("title") or item.get("name"),
        "url": item.get("html_url") or item.get("url"),
        "excerpt": item.get("description") or item.get("excerpt") or "",
        "published_at": item.get("updated_at") or item.get("updatedAt") or item.get("published_at"),
        "stars": item.get("stargazers_count") or item.get("stargazersCount") or item.get("stars"),
        "language": item.get("language") or ((item.get("primaryLanguage") or {}).get("name") if isinstance(item.get("primaryLanguage"), dict) else None),
        "license": (item.get("license") or {}).get("spdx_id") if isinstance(item.get("license"), dict) else item.get("license"),
        "source": "github-rest-api" if method == "rest" else "github-" + method,
        "retrieval_method": method,
        "evidence_level": "discovery",
    }


def _gh_search(query: str, limit: int) -> list[dict[str, Any]]:
    if shutil.which("gh") is None:
        return []
    try:
        env = os.environ.copy()
        env["GH_PROMPT_DISABLED"] = "1"
        result = subprocess.run(
            ["gh", "search", "repos", query, "--limit", str(limit), "--json", "fullName,url,description,updatedAt,stargazersCount,primaryLanguage"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            env=env,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    return [_repo_result(item, "gh-cli") for item in payload[:limit] if isinstance(item, dict)] if isinstance(payload, list) else []


def _generic_repo_search(query: str, limit: int) -> list[dict[str, Any]]:
    module_spec = importlib.util.spec_from_file_location(
        "research_router_platform_discovery", Path(__file__).with_name("platform_discovery.py")
    )
    if module_spec is None or module_spec.loader is None:
        return []
    module = importlib.util.module_from_spec(module_spec)
    try:
        module_spec.loader.exec_module(module)
        payload = module.discover("github", [query], limit, TIMEOUT)
    except Exception:
        return []
    results = []
    for item in payload.get("results", []) if isinstance(payload, dict) else []:
        url = item.get("url", "")
        parsed = urlparse(url)
        if parsed.hostname not in {"github.com", "www.github.com"}:
            continue
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2 or parts[0].lower() in {"topics", "collections", "orgs", "settings", "marketplace"}:
            continue
        result = _repo_result({**item, "repository": f"{parts[0]}/{parts[1]}"}, "generic-web-discovery")
        results.append(result)
        if len(results) >= limit:
            break
    return results


def _snapshot_readme(snapshot: dict[str, Any]) -> tuple[str | None, str | None]:
    for candidate in ("README.md", "README.MD", "README.rst", "README.txt", "README"):
        try:
            result = local_file(snapshot["root"], candidate)
            return result["content"], result["retrieval_method"]
        except (GitHubError, ValueError):
            continue
    return None, None


def _readme_via_raw(repo: str, ref: str) -> tuple[str | None, str | None]:
    for candidate in ("README.md", "README.MD", "README.rst", "README.txt", "README"):
        try:
            result = raw_file(repo, candidate, ref)
        except GitHubError:
            continue
        if result is not None:
            return result["content"], result["retrieval_method"]
    return None, None


def _tree_via_snapshot(
    repo: str,
    ref: str | None,
    limit: int,
    reason: str | None = None,
    size_kb: int | None = None,
) -> dict[str, Any]:
    snapshot = create_snapshot(repo, ref, size_kb, probe_metadata=False)
    result = local_tree(snapshot["root"], limit)
    result.update({
        "mode": "tree",
        "retrieval_method": "local-snapshot",
        "snapshot_root": snapshot["root"],
        "snapshot_method": snapshot["retrieval_method"],
        "ref": snapshot.get("ref"),
        "commit": snapshot.get("commit"),
        "temporary": True,
        "api_budget": api_budget(),
    })
    if reason:
        result["fallback_from"] = reason
    return result


def search(query: str, limit: int = 5) -> dict[str, Any]:
    failures: list[str] = []
    rest_error: GitHubError | None = None
    try:
        data = request_json("/search/repositories", {"q": query, "per_page": limit})
        items = data.get("items", []) if isinstance(data, dict) else []
        results = [_repo_result(item, "rest") for item in items[:limit] if isinstance(item, dict)]
        if results:
            return {
                "status": "ok",
                "mode": "search",
                "query": query,
                "results": results,
                "retrieval_method": "rest",
                "api_budget": api_budget(),
            }
        failures.append("GitHub REST repository search returned no results")
    except GitHubError as exc:
        rest_error = exc
        failures.append(str(exc))

    results = _gh_search(query, limit)
    method = "gh-cli"
    if not results:
        results = _generic_repo_search(query, limit)
        method = "generic-web-discovery"
    if results:
        return {
            "status": "partial",
            "mode": "search",
            "query": query,
            "results": results,
            "retrieval_method": method,
            "api_budget": api_budget(),
            "failures": failures,
        }
    status = "rate-limited" if rest_error and rest_error.status == "rate-limited" else "unavailable"
    return {
        "status": status,
        "mode": "search",
        "query": query,
        "results": [],
        "retrieval_method": "rest",
        "api_budget": api_budget(),
        "failures": failures + (["gh search repos unavailable"] if shutil.which("gh") else []) + ["generic github.com discovery returned no candidates"],
    }


def repository(repo: str) -> dict[str, Any]:
    slug = repository_slug(repo)
    try:
        data = request_json(_repo_path(slug))
    except GitHubError as exc:
        snapshot = create_snapshot(slug, probe_metadata=exc.status != "rate-limited")
        readme, readme_method = _snapshot_readme(snapshot)
        branch = snapshot.get("ref")
        return {
            "status": "partial",
            "mode": "repo",
            "repository": slug,
            "url": f"https://github.com/{slug}",
            "description": None,
            "default_branch": branch,
            "language": None,
            "license": None,
            "stars": None,
            "forks": None,
            "open_issues": None,
            "size_kb": None,
            "created_at": None,
            "updated_at": None,
            "pushed_at": None,
            "archived": None,
            "readme": readme,
            "readme_url": f"https://github.com/{slug}#readme" if readme else None,
            "source": "github-snapshot",
            "retrieval_method": readme_method or snapshot["retrieval_method"],
            "snapshot_method": snapshot["retrieval_method"],
            "snapshot_root": snapshot["root"],
            "temporary": True,
            "evidence_level": "detail" if readme else "partial",
            "api_budget": api_budget(),
            "failures": [str(exc), *snapshot.get("failures", [])],
        }
    if not isinstance(data, dict):
        raise GitHubError("GitHub repository endpoint returned an unexpected response")
    readme = None
    readme_method = None
    failures = []
    branch = data.get("default_branch")
    remaining = API_BUDGET.get("remaining")
    if isinstance(branch, str) and remaining is not None and remaining <= 1:
        readme, readme_method = _readme_via_raw(slug, branch)
    else:
        try:
            readme_data = request_json(_repo_path(slug, "/readme"))
            readme = _decode_file(readme_data)
            readme_method = "rest"
        except GitHubError as exc:
            failures.append(str(exc))
            if isinstance(branch, str):
                readme, readme_method = _readme_via_raw(slug, branch)
    if readme is None and isinstance(branch, str):
        try:
            snapshot = create_snapshot(slug, branch, data.get("size"), probe_metadata=False)
            readme, readme_method = _snapshot_readme(snapshot)
            snapshot_root = snapshot["root"]
        except GitHubError as exc:
            failures.append(str(exc))
            snapshot_root = None
    else:
        snapshot_root = None
    return {
        "status": "ok" if readme is not None else "partial",
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
        "size_kb": data.get("size"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "pushed_at": data.get("pushed_at"),
        "archived": data.get("archived"),
        "readme": readme,
        "readme_url": f"https://github.com/{slug}#readme" if readme is not None else None,
        "source": "github-rest-api",
        "retrieval_method": "rest",
        "readme_retrieval_method": readme_method,
        "snapshot_root": snapshot_root,
        "temporary": bool(snapshot_root),
        "api_budget": api_budget(),
        "failures": failures,
        "evidence_level": "detail" if readme is not None else "partial",
    }


def tree(repo: str, limit: int = 5000, snapshot: str | None = None) -> dict[str, Any]:
    if snapshot:
        result = local_tree(snapshot, limit)
        return {**result, "mode": "tree", "retrieval_method": "local-snapshot"}
    slug = repository_slug(repo)
    snapshot_attempted = False
    try:
        metadata = request_json(_repo_path(slug))
        branch = metadata.get("default_branch") if isinstance(metadata, dict) else None
        size_kb = metadata.get("size") if isinstance(metadata, dict) and isinstance(metadata.get("size"), int) else None
        if not isinstance(branch, str) or not branch:
            raise GitHubError("GitHub repository has no reported default branch")
        if API_BUDGET.get("remaining") is not None and API_BUDGET["remaining"] <= 1:
            snapshot_attempted = True
            return _tree_via_snapshot(slug, branch, limit, "GitHub REST request budget is low", size_kb)
        data = request_json(_repo_path(slug, f"/git/trees/{quote(branch, safe='')}"), {"recursive": 1})
        if not isinstance(data, dict):
            raise GitHubError("GitHub tree endpoint returned an unexpected response")
        entries = data.get("tree", [])
        if data.get("truncated"):
            try:
                return _tree_via_snapshot(slug, branch, limit, "GitHub REST tree was truncated", size_kb)
            except GitHubError as fallback:
                entries = data.get("tree", [])
                fallback_note = str(fallback)
        else:
            fallback_note = None
        items = [
            {"path": item.get("path"), "type": item.get("type"), "size": item.get("size"), "sha": item.get("sha")}
            for item in entries[:limit]
            if isinstance(item, dict)
        ]
        return {
            "status": "partial" if fallback_note else "ok",
            "mode": "tree",
            "repository": slug,
            "default_branch": branch,
            "truncated": bool(data.get("truncated")) or len(entries) > limit,
            "count": len(items),
            "results": items,
            "source": "github-rest-api",
            "retrieval_method": "rest",
            "api_budget": api_budget(),
            "fallback_error": fallback_note,
            "evidence_level": "detail",
        }
    except GitHubError as exc:
        if snapshot_attempted:
            raise GitHubError(f"GitHub REST budget was low and snapshot fallback failed: {exc}", exc.status) from exc
        try:
            return _tree_via_snapshot(slug, locals().get("branch"), limit, str(exc), locals().get("size_kb"))
        except GitHubError as fallback:
            raise GitHubError(f"REST tree failed and snapshot fallback failed: {fallback}", fallback.status) from exc


def file(repo: str, path: str, ref: str | None = None, snapshot: str | None = None) -> dict[str, Any]:
    slug = repository_slug(repo)
    clean_path = _safe_repo_path(path)
    snapshot_result = None
    snapshot_error = None
    tried_raw: set[str] = set()

    def read_raw(candidate_ref: str) -> dict[str, Any] | None:
        if candidate_ref in tried_raw:
            return None
        tried_raw.add(candidate_ref)
        try:
            return raw_file(slug, clean_path, candidate_ref)
        except GitHubError:
            return None

    if not snapshot:
        try:
            snapshot_result = create_snapshot(slug, ref)
        except GitHubError as exc:
            snapshot_error = exc
        else:
            try:
                local = local_file(snapshot_result["root"], clean_path)
            except GitHubError as exc:
                snapshot_error = exc
                ref = ref or snapshot_result.get("ref")
                snapshot = snapshot_result["root"]
            else:
                return {
                    **local,
                    "snapshot_root": snapshot_result["root"],
                    "snapshot_method": snapshot_result["retrieval_method"],
                    "temporary": True,
                    "api_budget": api_budget(),
                }
    if snapshot:
        try:
            return local_file(snapshot, clean_path)
        except GitHubError as local_error:
            _, snapshot_metadata = _snapshot_metadata(snapshot)
            ref = ref or snapshot_metadata.get("ref")
            if ref:
                raw = read_raw(ref)
                if raw is not None:
                    return {**raw, "fallback_from": "local-snapshot", "api_budget": api_budget()}
            try:
                data = request_json(_repo_path(slug, "/contents/" + quote(clean_path, safe="/")), {"ref": ref} if ref else None)
                return {
                    "mode": "file",
                    "repository": slug,
                    "path": clean_path,
                    "ref": ref,
                    "url": data.get("html_url") if isinstance(data, dict) else None,
                    "content": _decode_file(data),
                    "size": data.get("size") if isinstance(data, dict) else None,
                    "source": "github-rest-api",
                    "retrieval_method": "rest",
                    "fallback_from": "local-snapshot",
                    "api_budget": api_budget(),
                    "evidence_level": "detail",
                }
            except GitHubError as rest_error:
                status = rest_error.status if rest_error.status == "rate-limited" else local_error.status
                raise GitHubError(f"snapshot, raw, and REST file retrieval failed: {rest_error}", status) from local_error
    if ref:
        raw = read_raw(ref)
        if raw is not None:
            return {**raw, "api_budget": api_budget()}
    branch = ref
    failures = [str(snapshot_error)] if snapshot_error else []
    if not branch:
        metadata_error = snapshot_error
        if metadata_error is None:
            try:
                metadata = request_json(_repo_path(slug))
                branch = metadata.get("default_branch") if isinstance(metadata, dict) else None
            except GitHubError as exc:
                metadata_error = exc
                failures.append(str(exc))
        if metadata_error is not None:
            if metadata_error is not snapshot_error:
                failures.append(str(metadata_error))
            for candidate in ("main", "master"):
                raw = read_raw(candidate)
                if raw is not None:
                    return {**raw, "failures": failures, "api_budget": api_budget()}
    if branch:
        raw = read_raw(branch)
        if raw is not None:
            return {**raw, "api_budget": api_budget()}
    suffix = "/contents/" + quote(clean_path, safe="/")
    params = {"ref": branch} if branch else None
    data = request_json(_repo_path(slug, suffix), params)
    text = _decode_file(data)
    return {
        "status": "ok",
        "mode": "file",
        "repository": slug,
        "path": clean_path,
        "ref": branch,
        "url": data.get("html_url") if isinstance(data, dict) else None,
        "content": text,
        "size": data.get("size") if isinstance(data, dict) else None,
        "source": "github-rest-api",
        "retrieval_method": "rest",
        "api_budget": api_budget(),
        "evidence_level": "detail",
    }


def collection(repo: str, mode: str, limit: int = 10, snapshot: str | None = None) -> dict[str, Any]:
    slug = repository_slug(repo)
    if mode == "commits" and snapshot:
        root, metadata = _snapshot_metadata(snapshot)
        if not (root / ".git").is_dir():
            return {
                "status": "partial",
                "mode": mode,
                "repository": slug,
                "results": [],
                "source": "github-snapshot",
                "retrieval_method": "local-snapshot",
                "snapshot_method": metadata.get("retrieval_method"),
                "note": "archive snapshots do not include commit history",
            }
        result = _run_git(["log", f"-n{limit}", "--format=%H%x09%cs%x09%s"], cwd=root)
        if result.returncode != 0:
            raise GitHubError("could not read commit metadata from local snapshot")
        rows = []
        for line in result.stdout.splitlines():
            fields = line.split("\t", 2)
            if len(fields) == 3:
                rows.append({"sha": fields[0][:12], "published_at": fields[1], "title": fields[2]})
        return {
            "status": "ok" if rows else "partial",
            "mode": mode,
            "repository": slug,
            "results": rows,
            "source": "github-snapshot",
            "retrieval_method": "local-snapshot",
            "snapshot_method": metadata.get("retrieval_method"),
            "ref": metadata.get("ref"),
        }
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
    return {
        "status": "ok" if results else "partial",
        "mode": mode,
        "repository": slug,
        "results": results,
        "source": "github-rest-api",
        "retrieval_method": "rest",
        "api_budget": api_budget(),
        "evidence_level": "detail",
    }


def runtime() -> dict[str, Any]:
    return {
        "status": "ok",
        "mode": "runtime",
        "git": "installed" if shutil.which("git") else "missing",
        "gh": "installed-unverified" if shutil.which("gh") else "missing",
        "token_configured": bool(configured_token()),
        "api_budget": api_budget(),
    }


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
        if name in {"tree", "commits"}:
            command.add_argument("--snapshot")
    file_parser = subparsers.add_parser("file", help="Read one selected public repository file")
    file_parser.add_argument("--repo", required=True)
    file_parser.add_argument("--path", required=True)
    file_parser.add_argument("--ref")
    file_parser.add_argument("--snapshot")
    snapshot_parser = subparsers.add_parser("snapshot", help="Create a temporary shallow Git or source archive snapshot")
    snapshot_parser.add_argument("--repo", required=True)
    snapshot_parser.add_argument("--ref")
    snapshot_parser.add_argument("--size-kb", type=int, help="Repository size from an earlier metadata result")
    local_tree_parser = subparsers.add_parser("local-tree", help="List files from a route snapshot")
    local_tree_parser.add_argument("--snapshot", required=True)
    local_tree_parser.add_argument("--limit", type=int, default=5000)
    local_file_parser = subparsers.add_parser("local-file", help="Read one selected file from a route snapshot")
    local_file_parser.add_argument("--snapshot", required=True)
    local_file_parser.add_argument("--path", required=True)
    local_find_parser = subparsers.add_parser("local-find", help="Find candidate paths in a route snapshot")
    local_find_parser.add_argument("--snapshot", required=True)
    local_find_parser.add_argument("--pattern", required=True)
    local_find_parser.add_argument("--limit", type=int, default=100)
    cleanup_parser = subparsers.add_parser("cleanup", help="Remove a snapshot created by this adapter")
    cleanup_parser.add_argument("--snapshot", required=True)
    subparsers.add_parser("runtime", help="Probe optional local GitHub tools without changing their configuration")
    args = parser.parse_args()
    limit = getattr(args, "limit", 1)
    if not 1 <= limit <= (MAX_ARCHIVE_FILES if args.mode == "local-find" else MAX_ARCHIVE_FILES if args.mode == "local-tree" else 5000 if args.mode == "tree" else 50):
        parser.error("limit is outside the supported range")
    try:
        if args.mode == "search":
            result = search(args.query, args.limit)
        elif args.mode == "repo":
            result = repository(args.repo)
        elif args.mode == "tree":
            result = tree(args.repo, args.limit, args.snapshot)
        elif args.mode == "file":
            result = file(args.repo, args.path, args.ref, args.snapshot)
        elif args.mode == "snapshot":
            result = create_snapshot(args.repo, args.ref, args.size_kb)
        elif args.mode == "local-tree":
            result = local_tree(args.snapshot, args.limit)
        elif args.mode == "local-file":
            result = local_file(args.snapshot, args.path)
        elif args.mode == "local-find":
            result = local_find(args.snapshot, args.pattern, args.limit)
        elif args.mode == "cleanup":
            result = cleanup_snapshot(args.snapshot)
        elif args.mode == "runtime":
            result = runtime()
        else:
            result = collection(args.repo, args.mode, args.limit, getattr(args, "snapshot", None))
    except (GitHubError, ValueError) as exc:
        status = exc.status if isinstance(exc, GitHubError) else "unavailable"
        result = {"status": status, "mode": args.mode, "error": str(exc), "results": [], "api_budget": api_budget()}
    if "status" not in result:
        has_data = bool(result.get("results", result.get("readme") or result.get("content")))
        result["status"] = "ok" if has_data else "partial"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"ok", "partial"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
