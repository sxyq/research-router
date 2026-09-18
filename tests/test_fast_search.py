import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "fast_search.py"
SPEC = importlib.util.spec_from_file_location("fast_search", SCRIPT)
fast_search = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(fast_search)


class FastSearchTests(unittest.TestCase):
    def args(self, **values):
        defaults = {
            "query": "agent",
            "limit": 2,
            "timeout": 1,
            "base_url": None,
            "feed_url": None,
            "category": None,
            "tag": None,
            "page": 1,
            "language": "en",
        }
        defaults.update(values)
        return SimpleNamespace(**defaults)

    def test_github_results_are_compact_discovery_records(self):
        original = fast_search.request_json
        fast_search.request_json = lambda *args, **kwargs: {
            "items": [
                {
                    "full_name": "example/research",
                    "html_url": "https://github.com/example/research",
                    "description": "A research tool",
                    "updated_at": "2026-09-18T00:00:00Z",
                    "stargazers_count": 12,
                }
            ]
        }
        try:
            results = fast_search.search_github(self.args())
        finally:
            fast_search.request_json = original
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "github")
        self.assertEqual(results[0]["evidence_level"], "discovery")
        self.assertNotIn("raw", results[0])

    def test_arxiv_atom_is_normalized(self):
        xml = b"""<?xml version='1.0' encoding='UTF-8'?>
        <feed xmlns='http://www.w3.org/2005/Atom'>
          <entry>
            <id>https://arxiv.org/abs/1234.5678</id>
            <title>  Agent Search  </title>
            <summary> A short abstract. </summary>
            <published>2026-09-18T00:00:00Z</published>
          </entry>
        </feed>"""
        original = fast_search.request_bytes
        fast_search.request_bytes = lambda *args, **kwargs: xml
        try:
            results = fast_search.search_arxiv(self.args(query="agent search"))
        finally:
            fast_search.request_bytes = original
        self.assertEqual(results[0]["title"], "Agent Search")
        self.assertEqual(results[0]["url"], "https://arxiv.org/abs/1234.5678")
        self.assertEqual(results[0]["evidence_level"], "discovery")

    def test_rss_supports_atom_links(self):
        xml = b"""<?xml version='1.0' encoding='UTF-8'?>
        <feed xmlns='http://www.w3.org/2005/Atom'>
          <entry>
            <title>One entry</title>
            <link href='https://example.com/one' />
            <summary>Summary</summary>
            <updated>2026-09-18T00:00:00Z</updated>
          </entry>
        </feed>"""
        original = fast_search.request_bytes
        fast_search.request_bytes = lambda *args, **kwargs: xml
        try:
            results = fast_search.search_rss(self.args(feed_url="https://example.com/feed"))
        finally:
            fast_search.request_bytes = original
        self.assertEqual(results[0]["url"], "https://example.com/one")
        self.assertEqual(results[0]["excerpt"], "Summary")


if __name__ == "__main__":
    unittest.main()
