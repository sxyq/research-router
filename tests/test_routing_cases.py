import json
import unittest
from pathlib import Path


CASES = Path(__file__).parent / "routing-cases" / "basic-cases.json"


class RoutingCaseFormatTests(unittest.TestCase):
    def test_cases_are_named_requests_with_expectations(self):
        cases = json.loads(CASES.read_text(encoding="utf-8"))
        self.assertIsInstance(cases, list)
        self.assertTrue(cases)
        names = []
        for case in cases:
            self.assertIsInstance(case, dict)
            self.assertIsInstance(case.get("name"), str)
            self.assertTrue(case["name"].strip())
            self.assertIsInstance(case.get("request"), str)
            self.assertTrue(case["request"].strip())
            self.assertTrue(
                "expected" in case or "semantic_expectations" in case,
                f"{case['name']} needs expected or semantic_expectations",
            )
            names.append(case["name"])
        self.assertEqual(len(names), len(set(names)))

    def test_deep_cases_capture_default_breadth_and_explicit_scope(self):
        cases = {item["name"]: item for item in json.loads(CASES.read_text(encoding="utf-8"))}
        default = cases["deep-default-multi-platform"]["semantic_expectations"]
        explicit = cases["deep-youtube-only"]["expected"]
        self.assertEqual(default["depth"], "deep")
        self.assertEqual(default["explicit_platforms"], [])
        self.assertGreaterEqual(default["minimum_platform_count"], 3)
        self.assertEqual(explicit["depth"], "deep")
        self.assertEqual(explicit["platforms"], ["youtube"])
        self.assertTrue(explicit["no_extra_platforms"])


if __name__ == "__main__":
    unittest.main()
