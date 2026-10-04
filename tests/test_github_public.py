import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "github_public.py"
SPEC = importlib.util.spec_from_file_location("github_public", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class GitHubPublicTests(unittest.TestCase):
    def test_repository_search_normalizes_public_metadata(self):
        payload = {"items": [{"full_name": "owner/project", "html_url": "https://github.com/owner/project", "description": "desc", "stargazers_count": 7, "updated_at": "2026-01-01", "language": "Python", "license": {"spdx_id": "MIT"}}]}
        with patch.object(MODULE, "request_json", return_value=payload) as request:
            result = MODULE.search("agent research", 5)
        request.assert_called_once_with("/search/repositories", {"q": "agent research", "per_page": 5})
        self.assertEqual(result["results"][0]["repository"], "owner/project")
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
        with patch.object(MODULE, "request_json", return_value=file):
            file_result = MODULE.file("owner/project", "src/app.py")
        self.assertEqual(tree_result["results"][0]["path"], "src/app.py")
        self.assertEqual(file_result["content"], "print('ok')")

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

    def test_rate_limit_is_reported_without_retry(self):
        error = MODULE.HTTPError("https://api.github.com/search/repositories", 403, "rate", {"X-RateLimit-Remaining": "0"}, None)
        with patch.object(MODULE, "urlopen", side_effect=error) as open_url:
            with self.assertRaisesRegex(MODULE.GitHubError, "rate limit"):
                MODULE.request_json("/search/repositories")
        open_url.assert_called_once()


if __name__ == "__main__":
    unittest.main()
