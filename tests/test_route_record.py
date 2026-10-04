import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate-route-record.py"
SPEC = importlib.util.spec_from_file_location("validate_route_record", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class RouteRecordTests(unittest.TestCase):
    def route(self):
        return {
            "route_id": "route-queries",
            "created_at": "2026-10-04T00:00:00+08:00",
            "scene": "open-source",
            "interaction_mode": "direct",
            "depth": "medium",
            "requirement": {
                "target": "research-router",
                "goal": "find source and community evidence",
                "capabilities": ["source"],
                "context": [],
                "constraints": ["open source"],
                "evidence": ["source", "forums"],
                "time": [],
                "explicit_platforms": ["github", "v2ex"],
            },
            "query_variants": ["research-router source", "research-router community"],
            "platforms": [
                {
                    "platform_id": "github",
                    "agent_id": "github-agent",
                    "tier": 1,
                    "queries": ["research-router repository source code"],
                    "skill_order": ["github-search", "github-analyze"],
                }
            ],
            "router_path": [{"stage": "requirement"}],
            "executed_leaf_skills": ["github-analyze"],
            "final_leaf_skills": ["github-analyze"],
            "source_coverage": {"status": "partial", "requested": ["source"], "covered": [], "missing": ["source"]},
            "stop_reason": "partial",
            "route_evaluation": {
                "problem_coverage": 5,
                "evidence_directness": 5,
                "recency": None,
                "deduplication": 10,
                "execution_cost": {"query_count": 1, "skill_calls": 2, "agent_count": 1},
                "unconfirmed_items": ["source"],
                "overall": 5,
                "method": "manual",
            },
            "status": "partial",
        }

    def test_requirement_and_platform_queries_validate(self):
        self.assertEqual(MODULE.validate_route(self.route()), [])

    def test_platform_queries_must_be_non_empty_strings(self):
        route = self.route()
        route["platforms"][0]["queries"] = [""]
        errors = MODULE.validate_route(route)
        self.assertTrue(any("queries" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
