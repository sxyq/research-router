import importlib.util
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "probe_runtime.py"
SPEC = importlib.util.spec_from_file_location("probe_runtime", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class RuntimeProbeTests(unittest.TestCase):
    def test_youtube_missing_executable_is_reported(self):
        with patch.object(MODULE.shutil, "which", return_value=None):
            result = MODULE.probe_platform("youtube")
        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["capability_status"], "unverified")

    def test_unregistered_platform_is_rejected_before_path_lookup(self):
        with self.assertRaisesRegex(MODULE.ProbeError, "not registered"):
            MODULE.probe_platform("../../README")

    def test_youtube_version_only_probe_stays_unverified(self):
        paths = {"yt-dlp": "/bin/yt-dlp", "deno": "/bin/deno"}
        with patch.object(MODULE.shutil, "which", side_effect=lambda name: paths.get(name)), patch.object(
            MODULE, "_version", return_value={"status": "ok", "version": "2026.01.01"}
        ):
            result = MODULE.probe_platform("youtube")
        self.assertEqual(result["status"], "runtime-unverified")
        self.assertEqual(result["executables"][0]["status"], "runtime-unverified")

    def test_youtube_missing_javascript_runtime_is_reported(self):
        paths = {"yt-dlp": "/bin/yt-dlp"}
        with patch.object(MODULE.shutil, "which", side_effect=lambda name: paths.get(name)), patch.object(
            MODULE, "_version", return_value={"status": "ok", "version": "2026.01.01"}
        ):
            result = MODULE.probe_platform("youtube")
        self.assertEqual(result["status"], "installed")
        self.assertEqual(result["missing_prerequisites"], ["javascript-runtime"])

    def test_twitter_missing_tools_are_reported_without_running_commands(self):
        with patch.object(MODULE.shutil, "which", return_value=None), patch.object(
            MODULE.subprocess, "run", side_effect=AssertionError("must not execute a missing command")
        ):
            result = MODULE.probe_platform("twitter-x")
        self.assertEqual(result["status"], "missing")

    def test_twitter_cli_without_explicit_credentials_requires_auth(self):
        with patch.object(MODULE.shutil, "which", side_effect=lambda name: "/bin/twitter" if name == "twitter" else None), patch.dict(
            MODULE.os.environ,
            {"TWITTER_AUTH_TOKEN": "", "TWITTER_CT0": ""},
        ), patch.object(MODULE.subprocess, "run", side_effect=AssertionError("Twitter CLI must not be executed")):
            result = MODULE.probe_platform("twitter-x")
        self.assertEqual(result["status"], "requires-session-auth")
        self.assertEqual(result["executables"][0]["credential_configured"], False)

    def test_twitter_explicit_credentials_are_not_emitted_or_verified(self):
        secret = "test-secret-never-print"
        paths = {"twitter": "/bin/twitter"}
        with patch.object(MODULE.shutil, "which", side_effect=lambda name: paths.get(name)), patch.dict(
            MODULE.os.environ,
            {"TWITTER_AUTH_TOKEN": secret, "TWITTER_CT0": "test-ct0"},
        ):
            result = MODULE.probe_platform("twitter-x")
        self.assertEqual(result["status"], "runtime-unverified")
        self.assertTrue(result["executables"][0]["credential_configured"])
        self.assertNotIn(secret, json.dumps(result))

    def test_probe_runs_only_for_explicitly_selected_platforms(self):
        output = io.StringIO()
        with patch.object(MODULE, "probe_platform", return_value={"platform_id": "youtube", "status": "missing"}) as probe:
            with redirect_stdout(output):
                status = MODULE.main(["probe_runtime", "--platform", "youtube"])
        self.assertEqual(status, 0)
        probe.assert_called_once_with("youtube")
        self.assertEqual(json.loads(output.getvalue())["results"][0]["status"], "missing")


if __name__ == "__main__":
    unittest.main()
