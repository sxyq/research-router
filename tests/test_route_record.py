import importlib.util
import json
import unittest
from pathlib import Path

try:
    import jsonschema
except ImportError:
    jsonschema = None


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate-route-record.py"
SCHEMA_PATH = SCRIPT.parents[1] / "schemas" / "route-record.schema.json"
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

    def test_requirement_is_required(self):
        route = self.route()
        route.pop("requirement")
        self.assertTrue(any("requirement" in error for error in MODULE.validate_route(route)))

    def test_direct_route_requires_base_query_platform_and_platform_query(self):
        cases = []
        route = self.route()
        route["query_variants"] = []
        cases.append((route, "query_variant"))
        route = self.route()
        route["platforms"] = []
        cases.append((route, "at least one platform"))
        route = self.route()
        route["platforms"][0]["queries"] = []
        cases.append((route, "queries must contain at least one query"))
        for route, message in cases:
            with self.subTest(message=message):
                self.assertTrue(any(message in error for error in MODULE.validate_route(route)))

    def test_direct_requirement_target_and_goal_must_be_non_empty(self):
        route = self.route()
        route["requirement"]["target"] = "  "
        errors = MODULE.validate_route(route)
        self.assertTrue(any("requirement.target" in error for error in errors))

    def test_explicit_platform_scope_is_preserved_in_route_record(self):
        route = self.route()
        route["requirement"]["explicit_platforms"] = ["youtube"]
        errors = MODULE.validate_route(route)
        self.assertTrue(any("outside explicit platform scope" in error for error in errors))

    def test_clarify_route_can_have_empty_queries_and_platforms(self):
        route = self.route()
        route["interaction_mode"] = "clarify"
        route["requirement"]["target"] = ""
        route["requirement"]["goal"] = ""
        route["query_variants"] = []
        route["platforms"] = []
        route["executed_leaf_skills"] = []
        route["final_leaf_skills"] = []
        route["platforms"] = [
            {"platform_id": "github", "agent_id": "github-agent", "skill_order": [], "queries": []}
        ]
        route["source_coverage"] = {"status": "unavailable", "requested": [], "covered": [], "missing": []}
        self.assertEqual(MODULE.validate_route(route), [])
        route["platforms"] = []
        self.assertEqual(MODULE.validate_route(route), [])

    @unittest.skipIf(jsonschema is None, "jsonschema is installed in CI for JSON Schema behavior tests")
    def test_route_schema_matches_direct_and_clarify_requirements(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
        valid_direct = self.route()
        self.assertEqual(list(validator.iter_errors(valid_direct)), [])

        for mutate in (
            lambda item: item.pop("requirement"),
            lambda item: item.update(query_variants=[]),
            lambda item: item.update(platforms=[]),
            lambda item: item["platforms"][0].update(queries=[]),
            lambda item: item["query_variants"].__setitem__(0, "   "),
            lambda item: item["requirement"].update(target="   "),
        ):
            invalid = self.route()
            mutate(invalid)
            with self.subTest(mutate=mutate):
                self.assertTrue(list(validator.iter_errors(invalid)))

        clarify = self.route()
        clarify["interaction_mode"] = "clarify"
        clarify["requirement"]["target"] = ""
        clarify["requirement"]["goal"] = ""
        clarify["query_variants"] = []
        clarify["platforms"] = [
            {"platform_id": "github", "agent_id": "github-agent", "skill_order": [], "queries": []}
        ]
        clarify["executed_leaf_skills"] = []
        clarify["final_leaf_skills"] = []
        clarify["source_coverage"] = {"status": "unavailable", "requested": [], "covered": [], "missing": []}
        self.assertEqual(list(validator.iter_errors(clarify)), [])
        clarify["platforms"] = []
        self.assertEqual(list(validator.iter_errors(clarify)), [])


if __name__ == "__main__":
    unittest.main()
