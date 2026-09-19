#!/usr/bin/env python3
"""Check and update this Skill from its official GitHub repository."""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_URL = "https://github.com/sxyq/research-router"
PROJECT_GIT_URL = f"{PROJECT_URL}.git"
PROJECT_API_URL = "https://api.github.com/repos/sxyq/research-router/commits/main"
ARCHIVE_URL = f"{PROJECT_URL}/archive/refs/heads/main.tar.gz"
CHECK_INTERVAL_SECONDS = 7 * 24 * 60 * 60
STATE_FILENAME = ".research-router-update-state.json"
USER_AGENT = "research-router/update-skill 1.0"
PRESERVED_NAMES = {".git", "records", "tuning", STATE_FILENAME}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def state_path(target: Path) -> Path:
    return target / STATE_FILENAME


def read_state(target: Path) -> dict[str, object]:
    path = state_path(target)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def write_state(target: Path, state: dict[str, object]) -> None:
    path = state_path(target)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def emit(payload: dict[str, object], exit_code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


def run_git(target: Path, arguments: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(target), *arguments],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def current_git_commit(target: Path) -> str | None:
    if shutil.which("git") is None:
        return None
    result = run_git(target, ["rev-parse", "HEAD"])
    if result.returncode != 0:
        return None
    commit = result.stdout.strip()
    return commit or None


def remote_commit_from_git() -> str | None:
    if shutil.which("git") is None:
        return None
    result = subprocess.run(
        ["git", "ls-remote", PROJECT_GIT_URL, "refs/heads/main"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return None
    fields = result.stdout.strip().split()
    return fields[0] if fields else None


def remote_commit_from_api() -> str:
    request = Request(PROJECT_API_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    commit = payload.get("sha") if isinstance(payload, dict) else None
    if not isinstance(commit, str) or not commit:
        raise RuntimeError("GitHub did not return a commit for main")
    return commit


def latest_remote_commit() -> str:
    commit = remote_commit_from_git()
    if commit:
        return commit
    return remote_commit_from_api()


def extract_archive(payload: bytes, destination: Path) -> Path:
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        root = destination.resolve()
        members = []
        for member in archive.getmembers():
            member_path = (destination / member.name).resolve()
            if os.path.commonpath([str(root), str(member_path)]) != str(root):
                raise RuntimeError(f"unsafe archive path: {member.name}")
            if member.isdev() or member.issym() or member.islnk():
                raise RuntimeError(f"unsupported archive entry: {member.name}")
            members.append(member)
        archive.extractall(destination, members=members)
    roots = [path for path in destination.iterdir() if path.is_dir()]
    if len(roots) != 1:
        raise RuntimeError("unexpected GitHub archive layout")
    return roots[0]


def copy_managed_files(source: Path, target: Path) -> int:
    copied = 0
    for item in source.iterdir():
        if item.name in PRESERVED_NAMES:
            continue
        destination = target / item.name
        if item.is_dir():
            shutil.copytree(item, destination, dirs_exist_ok=True)
            copied += sum(1 for path in item.rglob("*") if path.is_file())
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)
            copied += 1
    return copied


def apply_update(target: Path) -> int:
    request = Request(ARCHIVE_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/octet-stream"})
    with urlopen(request, timeout=60) as response:
        payload = response.read()
    with tempfile.TemporaryDirectory(prefix="research-router-update-") as temporary_name:
        temporary = Path(temporary_name)
        source = extract_archive(payload, temporary)
        return copy_managed_files(source, target)


def check_due(state: dict[str, object], force_check: bool) -> bool:
    if force_check:
        return True
    try:
        last_check = float(state.get("last_check_epoch", 0))
    except (TypeError, ValueError):
        last_check = 0
    return time.time() - last_check >= CHECK_INTERVAL_SECONDS


def base_payload(target: Path, state: dict[str, object]) -> dict[str, object]:
    return {
        "repository": PROJECT_URL,
        "target": str(target),
        "checked_at": state.get("checked_at"),
        "next_check_after": state.get("next_check_after"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Apply the remote Skill files when an update is available.")
    mode.add_argument("--check-only", action="store_true", help="Only check for an update.")
    parser.add_argument("--force-check", action="store_true", help="Ignore the seven-day check interval for an explicit update request.")
    parser.add_argument("--target", type=Path, help="Local Skill directory; defaults to the directory containing this script.")
    args = parser.parse_args()

    target = (args.target or Path(__file__).resolve().parents[1]).expanduser().resolve()
    if not target.is_dir():
        return emit({"status": "unavailable", "repository": PROJECT_URL, "target": str(target), "reason": "target directory does not exist"}, 2)

    state = read_state(target)
    if not check_due(state, args.force_check):
        payload = base_payload(target, state)
        payload.update({"status": "cooldown", "interval_days": 7, "remote_checked": False})
        return emit(payload)

    checked_at = iso_now()
    state.update({
        "last_check_epoch": time.time(),
        "checked_at": checked_at,
        "next_check_after": datetime.fromtimestamp(time.time() + CHECK_INTERVAL_SECONDS, timezone.utc).isoformat(),
    })
    try:
        remote_commit = latest_remote_commit()
    except (HTTPError, URLError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        state["last_result"] = "unavailable"
        try:
            write_state(target, state)
        except OSError:
            pass
        payload = base_payload(target, state)
        payload.update({"status": "unavailable", "remote_checked": False, "reason": str(exc)})
        return emit(payload, 2)

    previous_commit = state.get("installed_commit") or current_git_commit(target)
    state["remote_commit"] = remote_commit
    if previous_commit == remote_commit:
        state["installed_commit"] = remote_commit
        state["last_result"] = "up-to-date"
        write_state(target, state)
        payload = base_payload(target, state)
        payload.update({"status": "up-to-date", "remote_checked": True, "remote_commit": remote_commit})
        return emit(payload)

    if args.check_only or not args.apply:
        state["last_result"] = "update-available"
        write_state(target, state)
        payload = base_payload(target, state)
        payload.update({"status": "update-available", "remote_checked": True, "remote_commit": remote_commit, "installed_commit": previous_commit})
        return emit(payload)

    try:
        copied = apply_update(target)
    except (HTTPError, URLError, OSError, RuntimeError, tarfile.TarError) as exc:
        state["last_result"] = "apply-failed"
        write_state(target, state)
        payload = base_payload(target, state)
        payload.update({"status": "apply-failed", "remote_checked": True, "remote_commit": remote_commit, "reason": str(exc)})
        return emit(payload, 2)

    state.update({"installed_commit": remote_commit, "last_result": "updated"})
    write_state(target, state)
    payload = base_payload(target, state)
    payload.update({"status": "updated", "remote_checked": True, "remote_commit": remote_commit, "previous_commit": previous_commit, "copied_files": copied, "preserved": sorted(PRESERVED_NAMES)})
    return emit(payload)


if __name__ == "__main__":
    raise SystemExit(main())
