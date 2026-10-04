import importlib.util
import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "github_public.py"
SPEC = importlib.util.spec_from_file_location("github_public", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class GitHubPublicTests(unittest.TestCase):
    def setUp(self):
        MODULE.API_BUDGET.update({"limit": None, "remaining": None, "reset_at": None, "authenticated": False})

    def test_repository_search_normalizes_public_metadata(self):
        payload = {"items": [{"full_name": "owner/project", "html_url": "https://github.com/owner/project", "description": "desc", "stargazers_count": 7, "updated_at": "2026-01-01", "language": "Python", "license": {"spdx_id": "MIT"}}]}
        with patch.object(MODULE, "request_json", return_value=payload) as request:
            result = MODULE.search("agent research", 5)
        request.assert_called_once_with("/search/repositories", {"q": "agent research", "per_page": 5})
        self.assertEqual(result["results"][0]["repository"], "owner/project")
        self.assertEqual(result["results"][0]["retrieval_method"], "rest")
        self.assertEqual(result["results"][0]["evidence_level"], "discovery")

    def test_repository_includes_readme_and_repository_metadata(self):
        metadata = {"full_name": "owner/project", "html_url": "https://github.com/owner/project", "default_branch": "main", "license": {"spdx_id": "MIT"}}
        readme = {"encoding": "base64", "content": "IyBQcm9qZWN0"}
        with patch.object(MODULE, "request_json", side_effect=[metadata, readme]):
            result = MODULE.repository("owner/project")
        self.assertEqual(result["default_branch"], "main")
        self.assertEqual(result["readme"], "# Project")
        self.assertEqual(result["evidence_level"], "detail")

    def test_tree_and_selected_file_are_readable(self):
        metadata = {"default_branch": "main"}
        tree = {"tree": [{"path": "src/app.py", "type": "blob", "size": 30, "sha": "abc"}], "truncated": False}
        file = {"encoding": "base64", "content": "cHJpbnQoJ29rJyk="}
        with patch.object(MODULE, "request_json", side_effect=[metadata, tree]):
            tree_result = MODULE.tree("owner/project", 10)
        with patch.object(MODULE, "create_snapshot", side_effect=MODULE.GitHubError("snapshot unavailable")), patch.object(
            MODULE, "request_json", return_value=file
        ), patch.object(MODULE, "raw_file", return_value=None):
            file_result = MODULE.file("owner/project", "src/app.py")
        self.assertEqual(tree_result["results"][0]["path"], "src/app.py")
        self.assertEqual(file_result["content"], "print('ok')")

    def test_truncated_rest_tree_falls_back_to_snapshot(self):
        with patch.object(MODULE, "request_json", side_effect=[{"default_branch": "main", "size": 1}, {"tree": [], "truncated": True}]), patch.object(
            MODULE,
            "_tree_via_snapshot",
            return_value={"status": "ok", "mode": "tree", "retrieval_method": "local-snapshot", "results": []},
        ) as fallback:
            result = MODULE.tree("owner/project", 5)
        self.assertEqual(result["retrieval_method"], "local-snapshot")
        fallback.assert_called_once_with("owner/project", "main", 5, "GitHub REST tree was truncated", 1)

    def test_raw_failure_uses_selected_file_rest_fallback(self):
        payload = {"encoding": "base64", "content": "cHJpbnQoJ29rJyk=", "size": 10}
        with patch.object(MODULE, "create_snapshot", side_effect=MODULE.GitHubError("snapshot unavailable")), patch.object(
            MODULE, "raw_file", side_effect=MODULE.GitHubError("raw unavailable")
        ), patch.object(
            MODULE, "request_json", return_value=payload
        ):
            result = MODULE.file("owner/project", "src/app.py", "main")
        self.assertEqual(result["retrieval_method"], "rest")
        self.assertEqual(result["content"], "print('ok')")

    def test_issues_exclude_pull_requests_and_releases_are_normalized(self):
        issues = [
            {"number": 1, "title": "Bug", "state": "open", "html_url": "https://github.com/o/r/issues/1"},
            {"number": 2, "title": "PR", "pull_request": {}, "html_url": "https://github.com/o/r/pull/2"},
        ]
        with patch.object(MODULE, "request_json", return_value=issues):
            result = MODULE.collection("o/r", "issues", 10)
        self.assertEqual([row["number"] for row in result["results"]], [1])

    def test_invalid_repo_and_path_are_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.repository_slug("../private")
        with self.assertRaises(ValueError):
            MODULE.file("owner/project", "../secret")
        with self.assertRaises(ValueError):
            MODULE.repository_slug("/owner/project")
        with self.assertRaises(ValueError):
            MODULE.file("owner/project", "src//main.py")

    def test_rate_limit_is_reported_without_retry(self):
        error = MODULE.HTTPError("https://api.github.com/search/repositories", 403, "rate", {"X-RateLimit-Remaining": "0"}, None)
        with patch.object(MODULE, "urlopen", side_effect=error) as open_url:
            with self.assertRaisesRegex(MODULE.GitHubError, "rate limit"):
                MODULE.request_json("/search/repositories")
        open_url.assert_called_once()
        self.assertEqual(MODULE.API_BUDGET["remaining"], 0)

    def test_search_rate_limit_falls_back_to_domain_discovery(self):
        candidate = {"repository": "owner/project", "url": "https://github.com/owner/project", "title": "owner/project"}
        with patch.object(MODULE, "request_json", side_effect=MODULE.GitHubError("REST limit", "rate-limited")), patch.object(
            MODULE, "_gh_search", return_value=[]
        ), patch.object(MODULE, "_generic_repo_search", return_value=[candidate]):
            result = MODULE.search("project", 5)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["retrieval_method"], "generic-web-discovery")
        self.assertEqual(result["results"], [candidate])

    def test_search_uses_optional_gh_before_generic_discovery(self):
        result_row = {"repository": "owner/project", "url": "https://github.com/owner/project"}
        with patch.object(MODULE, "request_json", side_effect=MODULE.GitHubError("REST search limit", "rate-limited")), patch.object(
            MODULE, "_gh_search", return_value=[result_row]
        ) as gh_search, patch.object(MODULE, "_generic_repo_search") as generic_search:
            result = MODULE.search("project", 4)
        self.assertEqual(result["retrieval_method"], "gh-cli")
        self.assertEqual(result["status"], "partial")
        gh_search.assert_called_once_with("project", 4)
        generic_search.assert_not_called()

    def test_optional_gh_repository_search_normalizes_results(self):
        payload = [{
            "fullName": "owner/project",
            "url": "https://github.com/owner/project",
            "description": "A project",
            "updatedAt": "2026-10-01T00:00:00Z",
            "stargazersCount": 9,
            "primaryLanguage": {"name": "Python"},
        }]
        completed = MODULE.subprocess.CompletedProcess([], 0, json.dumps(payload), "")
        with patch.object(MODULE.shutil, "which", return_value="/usr/bin/gh"), patch.object(
            MODULE.subprocess, "run", return_value=completed
        ) as run:
            results = MODULE._gh_search("research agent", 5)
        self.assertEqual(results[0]["retrieval_method"], "gh-cli")
        self.assertEqual(results[0]["repository"], "owner/project")
        self.assertEqual(results[0]["language"], "Python")
        self.assertEqual(run.call_args.args[0][:4], ["gh", "search", "repos", "research agent"])

    def test_optional_token_is_used_without_appearing_in_results(self):
        class Response:
            headers = {"X-RateLimit-Limit": "5000", "X-RateLimit-Remaining": "4999", "X-RateLimit-Reset": "1791111111"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b'{"ok":true}'

        seen = []

        def open_request(request, timeout):
            seen.append(request)
            return Response()

        secret = "test-secret-token"
        with patch.dict(os.environ, {"GITHUB_TOKEN": secret}, clear=True), patch.object(MODULE, "urlopen", side_effect=open_request):
            result = MODULE.request_json("/rate_limit")
            budget = MODULE.api_budget()
        self.assertEqual(seen[0].get_header("Authorization"), f"Bearer {secret}")
        self.assertTrue(budget["authenticated"])
        self.assertTrue(budget["token_configured"])
        self.assertEqual(budget["remaining"], 4999)
        self.assertNotIn(secret, json.dumps({"result": result, "api_budget": budget}))

    def test_api_budget_does_not_infer_authentication_from_quota_limit(self):
        class Response:
            headers = {"X-RateLimit-Limit": "5000", "X-RateLimit-Remaining": "4999"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b'{"ok":true}'

        with patch.dict(os.environ, {}, clear=True), patch.object(MODULE, "urlopen", return_value=Response()):
            MODULE.API_BUDGET["authenticated"] = False
            MODULE.request_json("/rate_limit")
            budget = MODULE.api_budget()
        self.assertFalse(budget["authenticated"])

    def test_gh_token_is_a_supported_optional_environment_name(self):
        class Response:
            headers = {"X-RateLimit-Limit": "5000", "X-RateLimit-Remaining": "4999"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b'{"ok":true}'

        seen = []
        with patch.dict(os.environ, {"GH_TOKEN": "gh-secret"}, clear=True), patch.object(
            MODULE, "urlopen", side_effect=lambda request, timeout: seen.append(request) or Response()
        ):
            MODULE.request_json("/rate_limit")
        self.assertEqual(seen[0].get_header("Authorization"), "Bearer gh-secret")

    def test_git_missing_uses_archive_snapshot_and_local_reads(self):
        with tempfile.TemporaryDirectory() as temp_name:
            temp_root = Path(temp_name)
            snapshot_dir = temp_root / f"{MODULE.SNAPSHOT_PREFIX}test"
            repo_root = snapshot_dir / "repo"

            def make_archive(_slug, ref, _snapshot_dir, root):
                root.mkdir(parents=True)
                (root / "README.md").write_text("# local", encoding="utf-8")
                (root / "pyproject.toml").write_text("[project]", encoding="utf-8")
                (root / "tests").mkdir()
                (root / "tests" / "test_app.py").write_text("assert True", encoding="utf-8")
                return {"retrieval_method": "archive", "ref": ref or "main", "commit": None}

            def make_temp_dir(prefix):
                self.assertEqual(prefix, MODULE.SNAPSHOT_PREFIX)
                snapshot_dir.mkdir()
                return str(snapshot_dir)

            with patch.object(MODULE.shutil, "which", return_value=None), patch.object(
                MODULE.tempfile, "gettempdir", return_value=temp_name
            ), patch.object(MODULE.tempfile, "mkdtemp", side_effect=make_temp_dir), patch.object(
                MODULE, "request_json", return_value={"default_branch": "main", "size": 1}
            ), patch.object(MODULE, "_archive_snapshot", side_effect=make_archive
            ):
                snapshot = MODULE.create_snapshot("owner/project")
                with patch.object(MODULE, "urlopen", side_effect=AssertionError("local snapshot reads must not use the network")):
                    tree = MODULE.local_tree(snapshot["root"])
                    readme = MODULE.local_file(snapshot["root"], "README.md")
                    found = MODULE.local_find(snapshot["root"], "*.py")
                removed = MODULE.cleanup_snapshot(snapshot["root"])
            self.assertEqual(snapshot["retrieval_method"], "archive")
            self.assertEqual(readme["content"], "# local")
            self.assertEqual(readme["snapshot_method"], "archive")
            self.assertEqual(tree["snapshot_method"], "archive")
            self.assertIn("tests/test_app.py", [item["path"] for item in found["results"]])
            self.assertEqual(tree["total_count"], 3)
            self.assertTrue(removed["removed"])
            self.assertFalse(snapshot_dir.exists())

    def test_git_snapshot_is_preferred_when_available(self):
        with tempfile.TemporaryDirectory() as temp_name:
            snapshot_dir = Path(temp_name) / f"{MODULE.SNAPSHOT_PREFIX}test"

            def make_temp_dir(prefix):
                self.assertEqual(prefix, MODULE.SNAPSHOT_PREFIX)
                snapshot_dir.mkdir()
                return str(snapshot_dir)

            def make_git(_slug, ref, root):
                root.mkdir()
                return {"retrieval_method": "git-shallow", "ref": ref or "main", "commit": "abc1234"}

            with patch.object(MODULE.shutil, "which", return_value="/usr/bin/git"), patch.object(
                MODULE.tempfile, "gettempdir", return_value=temp_name
            ), patch.object(MODULE.tempfile, "mkdtemp", side_effect=make_temp_dir), patch.object(
                MODULE, "request_json", return_value={"default_branch": "main", "size": 1}
            ), patch.object(MODULE, "_git_snapshot", side_effect=make_git
            ), patch.object(MODULE, "_archive_snapshot") as archive:
                result = MODULE.create_snapshot("owner/project")
            self.assertEqual(result["retrieval_method"], "git-shallow")
            archive.assert_not_called()

    def test_large_repository_skips_git_and_uses_bounded_archive_route(self):
        with tempfile.TemporaryDirectory() as temp_name:
            snapshot_dir = Path(temp_name) / f"{MODULE.SNAPSHOT_PREFIX}large"

            def make_temp_dir(prefix):
                self.assertEqual(prefix, MODULE.SNAPSHOT_PREFIX)
                snapshot_dir.mkdir()
                return str(snapshot_dir)

            def make_archive(_slug, ref, _directory, root):
                root.mkdir(parents=True)
                (root / "README.md").write_text("# bounded", encoding="utf-8")
                return {"retrieval_method": "archive", "ref": ref, "commit": None}

            with patch.object(MODULE.shutil, "which", return_value="/usr/bin/git"), patch.object(
                MODULE.tempfile, "gettempdir", return_value=temp_name
            ), patch.object(MODULE.tempfile, "mkdtemp", side_effect=make_temp_dir), patch.object(
                MODULE, "_git_snapshot"
            ) as git_snapshot, patch.object(MODULE, "_archive_snapshot", side_effect=make_archive):
                result = MODULE.create_snapshot("owner/project", "main", MODULE.MAX_GIT_REPOSITORY_KB + 1)
            git_snapshot.assert_not_called()
            self.assertEqual(result["retrieval_method"], "archive")
            self.assertTrue(any("shallow clone skipped" in failure for failure in result["failures"]))

    def test_archive_rate_limit_remains_rate_limited_after_all_snapshot_methods_fail(self):
        with tempfile.TemporaryDirectory() as temp_name, patch.object(MODULE.shutil, "which", return_value=None), patch.object(
            MODULE.tempfile, "gettempdir", return_value=temp_name
        ), patch.object(MODULE, "request_json", return_value={"default_branch": "main", "size": 1}), patch.object(
            MODULE, "_archive_snapshot", side_effect=MODULE.GitHubError("archive HTTP 429", "rate-limited")
        ):
            with self.assertRaises(MODULE.GitHubError) as caught:
                MODULE.create_snapshot("owner/project")
        self.assertEqual(caught.exception.status, "rate-limited")

    def test_safe_archive_extracts_regular_files(self):
        payload = self.make_tar([("owner-project-main/README.md", b"# Project", tarfile.REGTYPE)])
        with tempfile.TemporaryDirectory() as temp_name:
            root = MODULE._extract_archive(payload, Path(temp_name))
            self.assertEqual((root / "README.md").read_text(encoding="utf-8"), "# Project")

    def test_archive_download_limit_is_enforced(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b"123"

        with patch.object(MODULE, "MAX_ARCHIVE_BYTES", 2), patch.object(MODULE, "urlopen", return_value=Response()):
            with self.assertRaisesRegex(MODULE.GitHubError, "exceeds"):
                MODULE._download_archive("https://codeload.github.com/owner/project/tar.gz/main")

    def test_archive_rejects_traversal_links_and_oversized_files(self):
        cases = [
            [("repo/../escape.txt", b"bad", tarfile.REGTYPE)],
            [("repo/link", b"", tarfile.SYMTYPE)],
            [("repo/hardlink", b"", tarfile.LNKTYPE)],
            [("repo/device", b"", tarfile.CHRTYPE)],
        ]
        for members in cases:
            with self.subTest(member=members[0][0]), tempfile.TemporaryDirectory() as temp_name:
                with self.assertRaises(MODULE.GitHubError):
                    MODULE._extract_archive(self.make_tar(members), Path(temp_name))
        oversized = self.make_tar([("repo/big.bin", b"123", tarfile.REGTYPE)])
        with tempfile.TemporaryDirectory() as temp_name, patch.object(MODULE, "MAX_SINGLE_FILE_BYTES", 2):
            with self.assertRaisesRegex(MODULE.GitHubError, "oversized"):
                MODULE._extract_archive(oversized, Path(temp_name))
        multi_file = self.make_tar([
            ("repo/a.txt", b"12", tarfile.REGTYPE),
            ("repo/b.txt", b"34", tarfile.REGTYPE),
        ])
        with tempfile.TemporaryDirectory() as temp_name, patch.object(MODULE, "MAX_EXTRACTED_BYTES", 3):
            with self.assertRaisesRegex(MODULE.GitHubError, "extraction limits"):
                MODULE._extract_archive(multi_file, Path(temp_name))
        with tempfile.TemporaryDirectory() as temp_name, patch.object(MODULE, "MAX_ARCHIVE_FILES", 1):
            with self.assertRaisesRegex(MODULE.GitHubError, "extraction limits"):
                MODULE._extract_archive(multi_file, Path(temp_name))

    def test_raw_file_uses_fixed_github_host_and_rejects_unsafe_components(self):
        with self.assertRaises(ValueError):
            MODULE.raw_file("owner/project", "../secret", "main")
        with self.assertRaises(ValueError):
            MODULE.raw_file("owner/project", "src/main.py", "../branch")

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b"print('ok')"

        seen = []

        def open_request(request, timeout):
            seen.append(request.full_url)
            return Response()

        with patch.object(MODULE, "urlopen", side_effect=open_request):
            result = MODULE.raw_file("owner/project", "src/main.py", "main")
        self.assertTrue(seen[0].startswith("https://raw.githubusercontent.com/"))
        self.assertEqual(result["retrieval_method"], "raw")

    def test_raw_redirect_outside_github_is_rejected(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self):
                return "https://example.com/redirected"

            def read(self, _limit):
                return b"unexpected"

        with patch.object(MODULE, "urlopen", return_value=Response()):
            with self.assertRaisesRegex(MODULE.GitHubError, "outside"):
                MODULE.raw_file("owner/project", "README.md", "main")

    def test_raw_file_response_size_is_bounded(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b"123"

        with patch.object(MODULE, "MAX_RAW_FILE_BYTES", 2), patch.object(MODULE, "urlopen", return_value=Response()):
            with self.assertRaisesRegex(MODULE.GitHubError, "exceeds"):
                MODULE.raw_file("owner/project", "README.md", "main")

    def test_runtime_probe_and_bundled_route_do_not_require_gh_or_token(self):
        with patch.object(MODULE.shutil, "which", return_value=None), patch.dict(os.environ, {}, clear=True):
            result = MODULE.runtime()
        self.assertEqual(result["git"], "missing")
        self.assertEqual(result["gh"], "missing")
        self.assertFalse(result["token_configured"])

    @staticmethod
    def make_tar(entries):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for name, data, kind in entries:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.size = len(data) if kind == tarfile.REGTYPE else 0
                info.linkname = "repo/README.md" if kind == tarfile.LNKTYPE else ""
                archive.addfile(info, io.BytesIO(data) if kind == tarfile.REGTYPE else None)
        return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
