import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluate-route.py"
SPEC = importlib.util.spec_from_file_location("evaluate_route", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class RouteEvaluationTests(unittest.TestCase):
    def test_uses_existing_scope_and_counts_sources(self):
        route = {
            "status": "partial",
            "query_variants": ["one", "two"],
            "platforms": [{"agent_id": "agent-1", "skill_order": ["skill-1"]}],
            "evidence": [
                {"status": "verified"},
                {"status": "partial"},
            ],
            "source_coverage": {
                "status": "partial",
                "requested": ["thread"],
                "covered": ["listing"],
                "missing": ["thread"],
                "recency_score": 7,
            },
        }
        rows = MODULE.source_rows(route)
        coverage = MODULE.build_source_coverage(route, rows)
        evaluation = MODULE.build_evaluation(route, coverage, rows)
        self.assertEqual(coverage["source_count"], 2)
        self.assertEqual(coverage["direct_source_count"], 1)
        self.assertEqual(evaluation["execution_cost"]["query_count"], 2)
        self.assertEqual(evaluation["execution_cost"]["skill_calls"], 1)
        self.assertEqual(evaluation["recency"], 7)

    def test_empty_route_is_unavailable(self):
        route = {"status": "failed", "query_variants": [], "platforms": []}
        coverage = MODULE.build_source_coverage(route, [])
        evaluation = MODULE.build_evaluation(route, coverage, [])
        self.assertEqual(coverage["status"], "unavailable")
        self.assertEqual(evaluation["problem_coverage"], 0)
        self.assertEqual(evaluation["overall"], 0)


if __name__ == "__main__":
    unittest.main()
