import importlib.util
import io
import json
from contextlib import redirect_stdout
import unittest
from pathlib import Path


def load(name: str):
    script = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, script)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


bilibili = load("bilibili_public")
v2ex = load("v2ex_public")
xueqiu = load("xueqiu_public")


class PublicAdapterTests(unittest.TestCase):
    def test_bilibili_search_normalizes_public_result(self):
        original = bilibili.request_json
        bilibili.request_json = lambda *args, **kwargs: {
            "code": 0,
            "data": {"result": [{"result_type": "video", "data": [{"title": "<em>Agent</em> workflow", "bvid": "BV1demo", "description": "demo", "author": "user", "duration": "1:00", "play": 12}]}]},
        }
        try:
            rows = bilibili.search("agent", 1, 5, 1)
        finally:
            bilibili.request_json = original
        self.assertEqual(rows[0]["title"], "Agent workflow")
        self.assertEqual(rows[0]["url"], "https://www.bilibili.com/video/BV1demo")
        self.assertEqual(rows[0]["evidence_level"], "discovery")

    def test_bilibili_api_error_is_reported(self):
        original = bilibili.request_json
        bilibili.request_json = lambda *args, **kwargs: {"code": -400, "message": "bad request"}
        try:
            with self.assertRaises(RuntimeError):
                bilibili.search("agent", 1, 5, 1)
        finally:
            bilibili.request_json = original

    def test_bilibili_empty_results_are_valid(self):
        original = bilibili.request_json
        bilibili.request_json = lambda *args, **kwargs: {"code": 0, "data": {"result": []}}
        try:
            self.assertEqual(bilibili.search("missing", 1, 5, 1), [])
        finally:
            bilibili.request_json = original

    def test_bilibili_cli_emits_json(self):
        original = bilibili.request_json
        bilibili.request_json = lambda *args, **kwargs: {"code": 0, "data": {"result": []}}
        output = io.StringIO()
        try:
            with redirect_stdout(output):
                result = bilibili.main(["bilibili_public.py", "--query", "agent", "--limit", "1"])
        finally:
            bilibili.request_json = original
        self.assertEqual(result, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["provider"], "bilibili-public")
        self.assertIn("results", payload)

    def test_v2ex_hot_topics_use_public_api_scope(self):
        original = v2ex.request_json
        v2ex.request_json = lambda *args, **kwargs: [{"id": 7, "title": "Topic", "content": "Body", "replies": 3, "node": {"name": "tech", "title": "Technology"}}]
        try:
            payload = v2ex.fetch("hot", "https://www.v2ex.com", 5, 1)
        finally:
            v2ex.request_json = original
        self.assertEqual(payload["results"][0]["id"], 7)
        self.assertEqual(payload["mode"], "hot")

    def test_v2ex_empty_results_are_valid(self):
        original = v2ex.request_json
        v2ex.request_json = lambda *args, **kwargs: []
        try:
            self.assertEqual(v2ex.fetch("hot", "https://www.v2ex.com", 5, 1)["results"], [])
        finally:
            v2ex.request_json = original

    def test_v2ex_node_requires_node_name(self):
        with self.assertRaises(ValueError):
            v2ex.fetch("node", "https://www.v2ex.com", 5, 1)

    def test_xueqiu_quote_and_hot_post_normalization(self):
        original = xueqiu.request_json
        responses = iter([
            {"data": {"quote": {"symbol": "SH600519", "name": "贵州茅台", "current": 1000}}},
            {"list": [{"data": '{"id": 1, "text": "<p>post</p>", "user": {"screen_name": "user"}, "target": "/123"}'}]},
        ])
        xueqiu.request_json = lambda *args, **kwargs: next(responses)
        try:
            quote = xueqiu.fetch("quote", None, "SH600519", 5, 1)
            posts = xueqiu.fetch("hot-posts", None, None, 5, 1)
        finally:
            xueqiu.request_json = original
        self.assertEqual(quote["quote"]["name"], "贵州茅台")
        self.assertEqual(posts["results"][0]["text"], "post")

    def test_xueqiu_empty_results_are_valid(self):
        original = xueqiu.request_json
        xueqiu.request_json = lambda *args, **kwargs: {"data": {"items": []}}
        try:
            self.assertEqual(xueqiu.fetch("hot-stocks", None, None, 5, 1)["results"], [])
        finally:
            xueqiu.request_json = original


if __name__ == "__main__":
    unittest.main()
