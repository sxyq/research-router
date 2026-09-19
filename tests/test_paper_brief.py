import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).parents[1] / "academic-evidence" / "scripts" / "extract_paper_brief.py"
SPEC = importlib.util.spec_from_file_location("extract_paper_brief", SCRIPT)
paper_brief = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(paper_brief)


class PaperBriefTests(unittest.TestCase):
    def test_brief_extracts_abstract_outline_and_author_contributions(self):
        pages = [
            "Agentic Search Systems\n\nAbstract\nWe introduce a bounded search planner.\n\n1 Introduction\nOur contributions\nWe make the following contributions: (1) a planner; (2) an evaluation.\n\n2 Method\nDetails.",
            "3 Experiments\nResults.\n\n4 Conclusion\nConclusion text.",
        ]
        result = paper_brief.build_paper_brief(pages, source="paper.pdf")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["retrieval_stage"], "paper-brief")
        self.assertIn("bounded search planner", result["abstract"]["text"])
        self.assertEqual(result["section_outline"][0], {"title": "Abstract", "page": 1})
        self.assertTrue(any(item["title"] == "2 Method" for item in result["section_outline"]))
        self.assertEqual(len(result["contributions"]), 1)
        self.assertEqual(result["contributions"][0]["type"], "author-stated")
        self.assertFalse(result["full_audit"])


if __name__ == "__main__":
    unittest.main()
