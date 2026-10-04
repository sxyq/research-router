#!/usr/bin/env python3
"""Probe only the registered local runtime for explicitly selected platforms."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = ROOT / "registry" / "platforms"
VERSION_TIMEOUT_SECONDS = 5


class ProbeError(ValueError):
    pass


def read_platform(platform_id: str) -> dict[str, Any]:
    try:
        index = json.loads((ROOT / "registry" / "platforms.index.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProbeError(f"cannot read platform Registry: {exc}") from exc
    registered = index.get("platforms", []) if isinstance(index, dict) else []
    if platform_id not in registered:
        raise ProbeError(f"platform id is not registered: {platform_id!r}")
    path = PLATFORMS / f"{platform_id}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProbeError(f"no local platform registry entry for {platform_id!r}") from exc
    if not isinstance(value, dict) or value.get("platform_id") != platform_id:
        raise ProbeError(f"invalid local platform registry entry for {platform_id!r}")
    return value


def _version(path: str, args: list[str]) -> dict[str, Any]:
    child_env = os.environ.copy()
    # Current OpenCLI documents --version as side-effect free, but its app
    # wrapper can inject this obsolete setting into child processes.
    child_env.pop("OPENCLI_DAEMON_PORT", None)
    try:
        completed = subprocess.run(
            [path, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=VERSION_TIMEOUT_SECONDS,
            env=child_env,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
    except OSError as exc:
        return {"status": "error", "reason": str(exc)}
    output = (completed.stdout or completed.stderr).strip()
    result: dict[str, Any] = {"status": "ok" if completed.returncode == 0 else "error"}
    if output:
        result["version"] = output.splitlines()[0][:120]
    if completed.returncode != 0:
        result["returncode"] = completed.returncode
    return result


def _check_candidate(spec: dict[str, Any]) -> dict[str, Any]:
    commands = spec.get("commands", [])
    if not isinstance(commands, list) or not all(isinstance(item, str) for item in commands):
        raise ProbeError(f"invalid executable declaration for {spec.get('id', '<unknown>')}")
    found = None
    for command in commands:
        executable_path = shutil.which(command)
        if executable_path:
            found = (command, executable_path)
            break
    candidate: dict[str, Any] = {"id": spec.get("id", "runtime"), "status": "missing"}
    if found is None:
        candidate["commands"] = commands
        return candidate

    command, executable_path = found
    candidate.update({"status": "installed", "command": command, "path": executable_path})
    probe_args = spec.get("probe_args")
    if probe_args is not None:
        if not isinstance(probe_args, list) or not all(isinstance(item, str) for item in probe_args):
            raise ProbeError(f"invalid version probe arguments for {candidate['id']}")
        version_result = _version(executable_path, probe_args)
        candidate["version_probe"] = version_result
        if version_result["status"] == "ok":
            candidate["status"] = "runtime-unverified"

    credential_env = spec.get("credential_env", [])
    if credential_env:
        if not isinstance(credential_env, list) or not all(isinstance(item, str) for item in credential_env):
            raise ProbeError(f"invalid credential environment declaration for {candidate['id']}")
        candidate["credential_configured"] = all(bool(os.environ.get(name)) for name in credential_env)
        candidate["credential_variables"] = credential_env
    if spec.get("session"):
        candidate["session_status"] = "not-probed"
        candidate["session_requirement"] = spec["session"]
        candidate["status"] = "runtime-unverified"
    return candidate


def probe_platform(platform_id: str) -> dict[str, Any]:
    platform = read_platform(platform_id)
    runtime = platform.get("runtime")
    if not isinstance(runtime, dict):
        return {
            "platform_id": platform_id,
            "status": "unavailable",
            "capability_status": "unverified",
            "reason": "No runtime probe is registered for this platform.",
        }

    executable_specs = runtime.get("executables", [])
    if not isinstance(executable_specs, list) or not all(isinstance(item, dict) for item in executable_specs):
        raise ProbeError(f"invalid runtime executable list for {platform_id}")
    candidates = [_check_candidate(spec) for spec in executable_specs]
    installed = [candidate for candidate in candidates if candidate["status"] != "missing"]
    result: dict[str, Any] = {
        "platform_id": platform_id,
        "capability_status": "unverified",
        "executables": candidates,
        "capabilities_require_live_test": runtime.get("capabilities_require_live_test", []),
    }

    if not installed:
        result["status"] = "missing"
        result["reason"] = "None of the registered runtime executables is installed."
        return result

    if platform_id == "twitter-x":
        opencli_present = any(item["id"] == "opencli" for item in installed)
        configured_auth = any(item.get("credential_configured") is True for item in installed)
        if opencli_present:
            result["status"] = "runtime-unverified"
            result["authentication"] = "browser session not inspected; platform command not run"
        elif configured_auth:
            result["status"] = "runtime-unverified"
            result["authentication"] = "explicit credential variables present; authentication not tested"
        else:
            result["status"] = "requires-session-auth"
            result["authentication"] = "requires explicit credentials or a permitted existing session"
        result["reason"] = "Executable presence does not verify Twitter/X search; no login or browser-cookie access was attempted."
        result["session_policy"] = runtime.get("session_policy", "")
        return result

    required_any = runtime.get("required_any", [])
    missing_requirements = []
    for requirement in required_any:
        if not isinstance(requirement, dict):
            raise ProbeError(f"invalid runtime prerequisite declaration for {platform_id}")
        commands = requirement.get("commands", [])
        if not isinstance(commands, list) or not all(isinstance(command, str) for command in commands):
            raise ProbeError(f"invalid runtime prerequisite commands for {platform_id}")
        if not any(shutil.which(command) for command in commands):
            missing_requirements.append(requirement.get("id", "runtime dependency"))
    if missing_requirements:
        result["status"] = "installed"
        result["missing_prerequisites"] = missing_requirements
        result["reason"] = "The executable is installed, but required local prerequisites are missing."
        return result

    result["status"] = "runtime-unverified"
    result["reason"] = "Version probe only; search, metadata, and subtitle retrieval were not run."
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--platform",
        action="append",
        required=True,
        help="canonical selected platform id; repeat to probe multiple selected platforms",
    )
    args = parser.parse_args(argv[1:])
    if len(set(args.platform)) != len(args.platform):
        parser.error("each selected platform may be listed only once")
    try:
        results = [probe_platform(platform_id) for platform_id in args.platform]
    except ProbeError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
