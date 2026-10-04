import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "academic-evidence" / "scripts" / "academic_public.py"
SPEC = importlib.util.spec_from_file_location("academic_public", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class AcademicPublicTests(unittest.TestCase):
    def test_crossref_metadata_includes_authors_venue_and_abstract(self):
        payload = {"message": {"DOI": "10.1234/example", "title": ["A Paper"], "author": [{"given": "Ada", "family": "Lovelace"}], "published-print": {"date-parts": [[2024, 2]]}, "container-title": ["Journal"], "abstract": "<jats:p>Summary</jats:p>"}}
        with patch.object(MODULE, "fetch", return_value=json.dumps(payload).encode()):
            result = MODULE.crossref_metadata("10.1234/example")
        self.assertEqual(result["authors"], ["Ada Lovelace"])
        self.assertEqual(result["venue"], "Journal")
        self.assertIn("Summary", result["abstract"])

    def test_arxiv_atom_metadata_returns_public_paper_urls(self):
        atom = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>https://arxiv.org/abs/2401.12345</id><title>Paper title</title><summary>Abstract text</summary><published>2024-01-02T00:00:00Z</published><author><name>Ada</name></author><category xmlns="http://arxiv.org/schemas/atom" term="cs.AI" /></entry></feed>'''
        with patch.object(MODULE, "fetch", return_value=atom):
            result = MODULE.arxiv_metadata("2401.12345")
        self.assertEqual(result["title"], "Paper title")
        self.assertEqual(result["authors"], ["Ada"])
        self.assertEqual(result["pdf_url"], "https://arxiv.org/pdf/2401.12345")

    def test_public_html_reader_returns_selected_passages(self):
        page = b'''<html><head><title>Study title</title><meta name="citation_author" content="Author A"><meta name="description" content="Abstract"></head><body><h1>Introduction</h1><p>Background context.</p><h2>Results</h2><p>Our method improves recall by 10 percent.</p><p>Unrelated conclusion.</p></body></html>'''
        with patch.object(MODULE, "fetch", return_value=page):
            result = MODULE.read_html("https://example.org/paper", ["improves recall"], 10)
        self.assertEqual(result["title"], "Study title")
        self.assertEqual(result["abstract"], "Abstract")
        self.assertEqual(result["selected_passages"], ["Our method improves recall by 10 percent."])
        self.assertEqual(result["evidence_level"], "public-html-body")

    def test_non_arxiv_body_does_not_require_pdf_package(self):
        page = b"<html><body><p>Evidence paragraph.</p></body></html>"
        with patch.object(MODULE, "fetch", return_value=page):
            result = MODULE.paper_read("https://publisher.example/paper", [], 10)
        self.assertEqual(result["selected_passages"], ["Evidence paragraph."])

    def test_local_or_invalid_urls_are_refused(self):
        for url in ("file:///etc/passwd", "http://localhost/private", "http://router.local/private"):
            with self.subTest(url=url), self.assertRaises(MODULE.AcademicError):
                MODULE.fetch(url)


if __name__ == "__main__":
    unittest.main()
