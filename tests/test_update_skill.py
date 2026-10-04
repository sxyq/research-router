import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update-skill.py"
SPEC = importlib.util.spec_from_file_location("update_skill", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class UpdateSkillTests(unittest.TestCase):
    def test_updater_copies_new_bundled_files_and_preserves_user_data(self):
        with tempfile.TemporaryDirectory(prefix="router-update-source-") as source_name, tempfile.TemporaryDirectory(prefix="router-update-target-") as target_name:
            source = Path(source_name)
            target = Path(target_name)
            for relative, content in (
                ("scripts/github_public.py", "github adapter"),
                ("academic-evidence/scripts/academic_public.py", "academic adapter"),
                ("scripts/platform_discovery.py", "platform adapter"),
                ("references/local/github-research/SKILL.md", "local skill"),
                ("registry/platform-domains.json", "domains"),
                ("THIRD_PARTY_NOTICES.md", "notices"),
            ):
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            for preserved in (".git/config", "records/private.jsonl", "tuning/private.md", MODULE.STATE_FILENAME):
                path = target / preserved
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("keep", encoding="utf-8")

            copied = MODULE.copy_managed_files(source, target)
            self.assertEqual(copied, 6)
            self.assertEqual((target / "scripts/github_public.py").read_text(encoding="utf-8"), "github adapter")
            self.assertEqual((target / "references/local/github-research/SKILL.md").read_text(encoding="utf-8"), "local skill")
            for preserved in (".git/config", "records/private.jsonl", "tuning/private.md", MODULE.STATE_FILENAME):
                self.assertEqual((target / preserved).read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
