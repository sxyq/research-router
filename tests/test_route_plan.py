import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "route_plan.py"
SPEC = importlib.util.spec_from_file_location("route_plan", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class RoutePlanTests(unittest.TestCase):
    def test_requirement_model_precedes_scene_and_depth(self):
        plan = MODULE.plan_request("帮我找几个类似 research-router 的开源 Skill，并查看实际源码实现")
        self.assertEqual(plan["interaction_mode"], "direct")
        self.assertEqual(plan["scene"], "open-source")
        self.assertEqual(plan["depth"], "deep")
        self.assertEqual(
            set(plan["requirement"]),
            {"target", "goal", "capabilities", "context", "constraints", "evidence", "time", "explicit_platforms"},
        )
        self.assertGreaterEqual(len(plan["query_variants"]), 20)
        github = next(row for row in plan["platforms"] if row["platform_id"] == "github")
        self.assertIn("github-search", github["skill_order"])
        self.assertIn("github-analyze", github["skill_order"])
        self.assertNotEqual(plan["query_variants"][:3], github["queries"][:3])

    def test_explicit_youtube_scope_overrides_deep_breadth(self):
        plan = MODULE.plan_request("只查 YouTube，深度分析这个工具最近的教程和评价")
        self.assertEqual(plan["depth"], "deep")
        self.assertEqual([row["platform_id"] for row in plan["platforms"]], ["youtube"])
        self.assertEqual(plan["platforms"][0]["tier"], 2)
        self.assertGreaterEqual(len(plan["query_variants"]), 20)
        rewritten = " ".join(plan["platforms"][0]["queries"])
        for term in ("tutorial", "workflow", "demo", "review"):
            self.assertIn(term, rewritten)

    def test_twitter_aliases_and_bare_x(self):
        for text in ("Twitter 上的开发者评价", "推特上的开发者评价", "查看 x.com 上的讨论"):
            self.assertIn("twitter-x", MODULE.alias_matches(text))
        self.assertNotIn("twitter-x", MODULE.alias_matches("研究 x 的含义"))

    def test_depth_controls_breadth_not_query_count(self):
        light = MODULE.plan_request("研究 research-router")
        medium = MODULE.plan_request("比较 research-router 在 GitHub 和 V2EX 的社区反馈")
        deep = MODULE.plan_request("跨平台深入研究 research-router 的实现、教程和社区反馈")
        self.assertEqual(light["depth"], "light")
        self.assertEqual(medium["depth"], "medium")
        self.assertEqual(deep["depth"], "deep")
        self.assertGreaterEqual(len(light["query_variants"]), 12)
        self.assertGreaterEqual(len(medium["query_variants"]), 16)
        self.assertGreaterEqual(len(deep["query_variants"]), 20)
        self.assertEqual(len(light["platforms"]), 1)
        self.assertGreaterEqual(len(deep["platforms"]), 3)

    def test_missing_target_uses_clarify(self):
        plan = MODULE.plan_request("帮我研究一下")
        self.assertEqual(plan["interaction_mode"], "clarify")


if __name__ == "__main__":
    unittest.main()
