import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update-experience.py"
SPEC = importlib.util.spec_from_file_location("update_experience", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class ExperienceTests(unittest.TestCase):
    def route(self):
        return {
            "route_id": "route-1",
            "created_at": "2026-09-16T00:00:00+08:00",
            "scene": "community",
            "depth": "medium",
            "query_variants": ["query"],
            "platforms": [
                {"platform_id": "52pojie", "agent_id": "agent-1", "skill_order": ["52pojie-research"]}
            ],
            "matched_skills": [{"skill_id": "52pojie-research", "reason": "public forum"}],
            "executed_leaf_skills": ["52pojie-research"],
            "final_leaf_skills": ["52pojie-research"],
            "source_coverage": {
                "status": "partial",
                "requested": ["thread"],
                "covered": ["listing"],
                "missing": ["replies"]
            },
            "route_evaluation": {
                "problem_coverage": 6,
                "evidence_directness": 8,
                "recency": 8,
                "deduplication": 10,
                "execution_cost": {"query_count": 1, "skill_calls": 1, "agent_count": 1},
                "unconfirmed_items": ["replies"],
                "overall": 8,
                "method": "manual"
            },
            "failures": [],
            "stop_reason": "partial"
        }

    def test_builds_skill_and_platform_records(self):
        skill_records, platform_records = MODULE.build_records(self.route())
        self.assertEqual(skill_records[0]["subject_id"], "52pojie-research")
        self.assertTrue(skill_records[0]["executed"])
        self.assertEqual(platform_records[0]["skill_order"], ["52pojie-research"])

    def test_append_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "skill.jsonl"
            records, _ = MODULE.build_records(self.route())
            self.assertEqual(MODULE.append_unique(path, records, False), [records[0]["experience_id"]])
            self.assertEqual(MODULE.append_unique(path, records, False), [])
            saved = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(saved), 1)


if __name__ == "__main__":
    unittest.main()
