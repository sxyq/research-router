import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "platform_discovery.py"
SPEC = importlib.util.spec_from_file_location("platform_discovery", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class PlatformDiscoveryTests(unittest.TestCase):
    def test_generic_web_discovery_is_domain_scoped_and_normalized(self):
        result = {
            "status": "ok",
            "platform_id": "reddit",
            "provider": "public-web-site-search",
            "domains": ["reddit.com"],
            "queries": ["agent search"],
            "results": [{"title": "A discussion", "url": "https://www.reddit.com/r/example/", "evidence_level": "discovery"}],
        }
        with patch.object(MODULE, "load_domains", return_value={"reddit": {"domains": ["reddit.com"]}}), patch.object(
            MODULE, "search_one", return_value=[{"title": "A discussion", "url": "https://www.reddit.com/r/example/", "excerpt": "text", "published_at": None, "source": "public-web-site-search", "platform_id": "reddit", "domain": "reddit.com", "query": "agent search", "evidence_level": "discovery"}]
        ) as search:
            output = MODULE.discover("reddit", ["agent search"], 5, 3)
        self.assertEqual(output["status"], "ok")
        self.assertEqual(output["results"][0]["platform_id"], "reddit")
        search.assert_called_once_with("reddit", "reddit.com", "agent search", 5, 3)

    def test_stackoverflow_uses_bundled_public_api_provider(self):
        expected = [{"title": "Question", "url": "https://stackoverflow.com/q/1", "source": "stackoverflow", "evidence_level": "discovery"}]
        with patch.object(MODULE, "load_domains", return_value={"stackoverflow": {"domains": ["stackoverflow.com"], "native_provider": "stackoverflow"}}), patch.object(
            MODULE, "native_search", return_value={"status": "ok", "provider": "stackoverflow", "results": expected}
        ) as native:
            output = MODULE.discover("stackoverflow", ["python api"], 5, 3)
        self.assertEqual(output["results"], expected)
        native.assert_called_once_with("stackoverflow", "stackoverflow", ["python api"], 5, 3, None)

    def test_wikipedia_catalog_uses_bundled_public_api_provider(self):
        expected = [{"title": "Transformer", "url": "https://en.wikipedia.org/wiki/Transformer", "source": "wikipedia", "evidence_level": "discovery"}]
        with patch.object(MODULE, "load_domains", return_value={"wikipedia": {"domains": ["wikipedia.org"], "native_provider": "wikipedia"}}), patch.object(
            MODULE, "native_search", return_value={"status": "ok", "provider": "wikipedia", "results": expected}
        ) as native:
            output = MODULE.discover("wikipedia", ["Transformer"], 5, 3)
        self.assertEqual(output["results"], expected)
        native.assert_called_once_with("wikipedia", "wikipedia", ["Transformer"], 5, 3, None)

    def test_discourse_needs_a_registered_or_supplied_public_base(self):
        with patch.object(MODULE, "load_domains", return_value={"discourse": {"domains": [], "native_provider": "discourse"}}):
            with self.assertRaisesRegex(MODULE.DiscoveryError, "base URL"):
                MODULE.discover("discourse", ["kernel"], 5, 3)

    def test_generic_discovery_filters_search_engine_results_outside_registered_domain(self):
        bing_rows = [{"url": "https://unrelated.example/article", "title": "wrong host"}]
        ddg_rows = [{"url": "https://www.reddit.com/r/example/", "title": "right host"}]
        with patch.object(MODULE, "search_bing_rss", return_value=bing_rows), patch.object(
            MODULE, "search_duckduckgo_html", return_value=ddg_rows
        ):
            rows = MODULE.search_one("reddit", "reddit.com", "query", 5, 3)
        self.assertEqual([row["title"] for row in rows], ["right host"])

    def test_unknown_platform_and_empty_domains_are_not_guessed(self):
        with self.assertRaisesRegex(MODULE.DiscoveryError, "no generic public discovery registration"):
            MODULE.discover("unknown", ["query"], 5, 3)


if __name__ == "__main__":
    unittest.main()
