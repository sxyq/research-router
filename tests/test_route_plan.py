import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "route_plan.py"
SPEC = importlib.util.spec_from_file_location("route_plan", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def agent_plan(*, platform_id="YouTube", depth="deep", queries=None):
    return {
        "requirement": {
            "target": "Claude Code",
            "goal": "了解最近如何使用 Claude Code 构建 research workflow",
            "capabilities": ["research workflow", "agent workflow"],
            "context": ["Claude Code"],
            "constraints": ["recent"],
            "evidence": ["video metadata", "subtitles when available"],
            "time": ["recent"],
            "explicit_platforms": ["油管"],
        },
        "interaction_mode": "direct",
        "scene": "community",
        "depth": depth,
        "query_variants": queries or ["query one", "query two", "query three"],
        "platforms": [
            {
                "platform_id": platform_id,
                "queries": ["Claude Code tutorial workflow", "Claude Code research demo"],
            }
        ],
        "router_path": [{"stage": "requirement"}, {"stage": "platform-selection"}],
    }


class RoutePlanTests(unittest.TestCase):
    def test_agent_plan_is_resolved_without_natural_language_inference(self):
        plan = MODULE.resolve_route_plan(agent_plan())
        self.assertEqual(plan["requirement"]["target"], "Claude Code")
        self.assertEqual(plan["requirement"]["explicit_platforms"], ["youtube"])
        self.assertEqual(plan["platforms"][0]["platform_id"], "youtube")
        self.assertEqual(plan["platforms"][0]["tier"], 2)
        self.assertEqual(
            plan["platforms"][0]["search_components"],
            ["generic-public-site-discovery", "youtube-yt-dlp"],
        )
        self.assertEqual(plan["platforms"][0]["adapter_type"], "generic-site-discovery-plus-optional-cli")
        self.assertEqual(
            plan["platforms"][0]["access_mode"],
            "public-generic-discovery; rich-video-runtime-optional",
        )
        self.assertEqual(plan["platforms"][0]["skill_order"], ["generic-platform-discovery"])

    def test_platform_alias_normalization_is_exact_and_bare_x_is_rejected(self):
        self.assertEqual(MODULE.canonicalize_platform("推特"), "twitter-x")
        self.assertEqual(MODULE.canonicalize_platform("x.com"), "twitter-x")
        self.assertEqual(MODULE.canonicalize_platform("YouTube"), "youtube")
        with self.assertRaises(MODULE.PlanError):
            MODULE.canonicalize_platform("x")
        with self.assertRaises(MODULE.PlanError):
            MODULE.canonicalize_platform("bug")

    def test_explicit_platform_scope_accepts_alias_and_canonical_id(self):
        plan = agent_plan(platform_id="YouTube")
        plan["requirement"]["explicit_platforms"] = ["油管"]
        self.assertEqual(MODULE.resolve_route_plan(plan)["platforms"][0]["platform_id"], "youtube")

    def test_explicit_platform_scope_rejects_additional_platform(self):
        plan = agent_plan()
        plan["platforms"].append({"platform_id": "github", "queries": ["Claude Code source"]})
        with self.assertRaisesRegex(MODULE.PlanError, "github.*outside explicit platform scope.*youtube"):
            MODULE.resolve_route_plan(plan)

    def test_multiple_explicit_platforms_accept_aliases(self):
        plan = agent_plan()
        plan["requirement"]["explicit_platforms"] = ["github", "推特"]
        plan["platforms"] = [
            {"platform_id": "GitHub", "queries": ["Claude Code repository"]},
            {"platform_id": "twitter-x", "queries": ["Claude Code developer discussion"]},
        ]
        resolved = MODULE.resolve_route_plan(plan)
        self.assertEqual(
            [row["platform_id"] for row in resolved["platforms"]],
            ["github", "twitter-x"],
        )

    def test_direct_route_requires_base_query(self):
        for queries in ([], [""]):
            plan = agent_plan()
            plan["query_variants"] = queries
            with self.subTest(queries=queries), self.assertRaises(MODULE.PlanError):
                MODULE.resolve_route_plan(plan)

    def test_direct_route_requires_platform_specific_query(self):
        for queries in ([], ["   "]):
            plan = agent_plan()
            plan["platforms"][0]["queries"] = queries
            with self.subTest(queries=queries), self.assertRaises(MODULE.PlanError):
                MODULE.resolve_route_plan(plan)

    def test_direct_route_requires_selected_platform(self):
        plan = agent_plan()
        plan["platforms"] = []
        with self.assertRaisesRegex(MODULE.PlanError, "at least one selected platform"):
            MODULE.resolve_route_plan(plan)

    def test_direct_route_requires_non_empty_target_and_goal(self):
        for field in ("target", "goal"):
            plan = agent_plan()
            plan["requirement"][field] = "  "
            with self.subTest(field=field), self.assertRaisesRegex(MODULE.PlanError, field):
                MODULE.resolve_route_plan(plan)

    def test_clarify_route_can_defer_queries_and_platform_selection(self):
        plan = agent_plan()
        plan["interaction_mode"] = "clarify"
        plan["requirement"]["target"] = ""
        plan["requirement"]["goal"] = ""
        plan["query_variants"] = []
        plan["platforms"] = []
        resolved = MODULE.resolve_route_plan(plan)
        self.assertEqual(resolved["query_variants"], [])
        self.assertEqual(resolved["platforms"], [])

    def test_clarify_route_still_enforces_explicit_platform_scope(self):
        plan = agent_plan()
        plan["interaction_mode"] = "clarify"
        plan["query_variants"] = []
        plan["platforms"] = [{"platform_id": "github", "queries": []}]
        with self.assertRaisesRegex(MODULE.PlanError, "github.*outside explicit platform scope.*youtube"):
            MODULE.resolve_route_plan(plan)

    def test_clarify_route_can_canonicalize_selected_platform_without_queries(self):
        plan = agent_plan()
        plan["interaction_mode"] = "clarify"
        plan["query_variants"] = []
        plan["platforms"] = [{"platform_id": "YouTube", "queries": []}]
        resolved = MODULE.resolve_route_plan(plan)
        self.assertEqual(resolved["platforms"][0]["platform_id"], "youtube")
        self.assertEqual(resolved["platforms"][0]["queries"], [])

    def test_registry_packet_preserves_agent_queries_without_truncation(self):
        queries = [f"semantic direction {index}" for index in range(37)]
        plan = agent_plan(queries=queries)
        plan["platforms"][0]["queries"] = queries[:23]
        resolved = MODULE.resolve_route_plan(plan)
        self.assertEqual(resolved["query_variants"], queries)
        self.assertEqual(resolved["platforms"][0]["queries"], queries[:23])

    def test_deep_packet_can_contain_multiple_registry_backed_platforms(self):
        plan = agent_plan(depth="deep")
        plan["requirement"]["explicit_platforms"] = []
        plan["platforms"] = [
            {"platform_id": "github", "queries": ["router implementation source"]},
            {"platform_id": "V2EX", "queries": ["research router 使用体验"]},
            {"platform_id": "推特", "queries": ["research-router developer experience"]},
        ]
        resolved = MODULE.resolve_route_plan(plan)
        self.assertEqual(
            [item["platform_id"] for item in resolved["platforms"]],
            ["github", "v2ex", "twitter-x"],
        )
        self.assertEqual(
            resolved["platforms"][0]["scripts"],
            ["scripts/github_public.py", "scripts/platform_discovery.py"],
        )
        self.assertEqual(resolved["platforms"][1]["scripts"], ["scripts/v2ex_public.py"])
        self.assertEqual(
            resolved["platforms"][2]["scripts"],
            ["scripts/platform_discovery.py", "scripts/probe_runtime.py"],
        )

    def test_unknown_platform_is_reported(self):
        plan = agent_plan(platform_id="unknown platform")
        with self.assertRaisesRegex(MODULE.PlanError, "unknown platform"):
            MODULE.resolve_route_plan(plan)

    def test_agent_semantic_planner_is_required(self):
        self.assertFalse(hasattr(MODULE, "plan_request"))
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("import re", source)
        self.assertNotIn("CAPABILITY_TERMS", source)
        self.assertNotIn("def extract_requirement", source)


if __name__ == "__main__":
    unittest.main()
