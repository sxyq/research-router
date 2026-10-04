import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PLATFORM_INDEX = json.loads((ROOT / "registry" / "platforms.index.json").read_text(encoding="utf-8"))
SKILLS = json.loads((ROOT / "registry" / "skills.index.json").read_text(encoding="utf-8"))["skills"]
SKILL_BY_ID = {skill["id"]: skill for skill in SKILLS}
SCRIPT = ROOT / "scripts" / "route_plan.py"
SPEC = importlib.util.spec_from_file_location("route_plan_fresh_install", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def make_plan(platform_id: str, depth: str) -> dict:
    return {
        "requirement": {
            "target": "fresh-install smoke",
            "goal": "verify bundled platform route",
            "capabilities": [],
            "context": [],
            "constraints": [],
            "evidence": ["public sources"],
            "time": [],
            "explicit_platforms": [platform_id],
        },
        "interaction_mode": "direct",
        "scene": "community",
        "depth": depth,
        "query_variants": ["public route smoke"],
        "platforms": [{"platform_id": platform_id, "queries": ["public route smoke"]}],
    }


class FreshInstallTests(unittest.TestCase):
    def test_every_active_and_catalog_depth_uses_only_bundled_skills(self):
        platforms = list(PLATFORM_INDEX["platforms"])
        platforms.extend(entry["platform_id"] for entry in PLATFORM_INDEX["catalog_only_platforms"])
        with tempfile.TemporaryDirectory(prefix="research-router-empty-codex-home-") as empty_codex_home:
            with patch.dict(os.environ, {"CODEX_HOME": empty_codex_home}):
                self.assertEqual(list(Path(empty_codex_home).iterdir()), [])
                for platform_id in platforms:
                    for depth in ("light", "medium", "deep"):
                        with self.subTest(platform=platform_id, depth=depth):
                            packet = MODULE.resolve_route_plan(make_plan(platform_id, depth))["platforms"][0]
                            self.assertTrue(packet["skill_order"])
                            for skill_id in packet["skill_order"]:
                                self.assertEqual(SKILL_BY_ID[skill_id]["availability"], "bundled")
                            for script in packet["scripts"]:
                                self.assertTrue((ROOT / script).is_file(), script)
                            self.assertTrue(
                                set(packet["optional_enhancements"]).issubset(SKILL_BY_ID)
                            )

    def test_github_and_academic_remain_bundled_for_all_depths_without_external_skills(self):
        with tempfile.TemporaryDirectory(prefix="research-router-empty-codex-home-") as empty_codex_home:
            with patch.dict(os.environ, {"CODEX_HOME": empty_codex_home}):
                for platform_id in ("github", "academic", "google-scholar"):
                    for depth in ("light", "medium", "deep"):
                        packet = MODULE.resolve_route_plan(make_plan(platform_id, depth))["platforms"][0]
                        self.assertEqual(packet["skill_order"], ["github-local"] if platform_id == "github" else ["academic-local"])
                        self.assertIn("optional_enhancements", packet)

    def test_autocli_is_never_in_a_default_route(self):
        for platform_id in [*PLATFORM_INDEX["platforms"], *(item["platform_id"] for item in PLATFORM_INDEX["catalog_only_platforms"])]:
            for depth in ("light", "medium", "deep"):
                packet = MODULE.resolve_route_plan(make_plan(platform_id, depth))["platforms"][0]
                self.assertNotIn("autocli", packet["skill_order"], f"{platform_id}/{depth}")


if __name__ == "__main__":
    unittest.main()
