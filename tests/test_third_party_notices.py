import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ThirdPartyNoticeTests(unittest.TestCase):
    def test_notice_states_no_upstream_source_was_vendored(self):
        notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8").lower()
        self.assertIn("no third-party source code was copied", notice)
        self.assertIn("autocli", notice)
        self.assertIn("license was not confirmed", notice)
        self.assertFalse((ROOT / "third_party").exists())


if __name__ == "__main__":
    unittest.main()
