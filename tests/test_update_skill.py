import importlib.util
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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


    def test_non_git_fresh_install_bootstraps_from_release_version(self):
        with tempfile.TemporaryDirectory(prefix="router-update-target-") as target_name:
            target = Path(target_name)
            (target / MODULE.VERSION_FILENAME).write_text("1.0.0\n", encoding="utf-8")
            argv = [
                "update-skill.py",
                "--check-only",
                "--force-check",
                "--target",
                str(target),
            ]
            output = io.StringIO()
            with patch.object(sys, "argv", argv), patch.object(
                MODULE, "current_git_commit", return_value=None
            ), patch.object(
                MODULE, "latest_remote_commit", return_value="abc123"
            ), patch.object(
                MODULE, "remote_release_version", return_value="1.0.0"
            ), contextlib.redirect_stdout(output):
                code = MODULE.main()

            self.assertEqual(code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["status"], "up-to-date")
            self.assertEqual(payload["remote_commit"], "abc123")
            self.assertEqual(payload["installed_version"], "1.0.0")
            state = MODULE.read_state(target)
            self.assertEqual(state["installed_commit"], "abc123")
            self.assertEqual(state["installed_version"], "1.0.0")

    def test_skill_policy_uses_periodic_check_only_and_never_auto_applies(self):
        root = Path(__file__).resolve().parents[1]
        skill = (root / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/update-skill.py --check-only", skill)
        self.assertIn("Never apply an update automatically.", skill)
        self.assertIn("python3 scripts/update-skill.py --force-check --apply", skill)


if __name__ == "__main__":
    unittest.main()
