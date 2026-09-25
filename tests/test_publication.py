from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from app import create_app, export_site
from garden import Arxiv, Garden, ROOT, atomic_write
from paper_config import validate_pipeline
from paper_pipeline import assemble
from paper_publication import publication_display
from paper_validation import validate_document


class PublicationTests(unittest.TestCase):
    def test_archive_is_not_proof_of_no_publication(self):
        cases = [
            ({"source": "https://arxiv.org/abs/2609.24359", "doi": "10.48550/arXiv.2609.24359"}, "arXiv", "2609.24359"),
            ({"source": "https://eprint.iacr.org/2026/123", "journal_ref": "Cryptology ePrint Archive"}, "IACR ePrint", "2026/123"),
            ({"source": "https://example.org/paper.pdf"}, "원문", ""),
        ]
        for metadata, archive, identifier in cases:
            with self.subTest(metadata=metadata):
                info = publication_display(metadata)
                self.assertEqual(info["archive_label"], archive)
                self.assertEqual(info["source_id"], identifier)
                self.assertIn("게재처 미확인", info["publication_label"])

    def test_journal_and_explicit_acceptance(self):
        base = {"source": "https://arxiv.org/abs/2609.00001"}
        self.assertEqual(publication_display({**base, "journal_ref": "Test Journal 12 (2026)"})["publication_label"], "Test Journal 12 (2026)")
        for note in ("Submitted to a workshop", "Not accepted at Conference", "12 pages, 5 figures"):
            self.assertIn("미확인", publication_display({**base, "publication_note": note})["publication_label"])
        self.assertEqual(publication_display({**base, "publication_note": "Accepted at AI4MFDD, ECCV 2026. 34 pages"})["publication_label"], "Accepted at AI4MFDD, ECCV 2026")
        self.assertEqual(publication_display({**base, "publication_note": "Accepted at Workshop (AI4MFDD), ECCV 2026. 34 pages"})["publication_short"], "AI4MFDD · ECCV 2026")
        self.assertEqual(publication_display({**base, "journal_ref": "IEEE Transactions on Information Forensics and Security"})["publication_short"], "IEEE TIFS")

    def test_arxiv_parser_preserves_publication_fields(self):
        xml = b'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
        <entry><id>https://arxiv.org/abs/2609.00001v1</id><title>Test</title><summary>Abstract</summary>
        <published>2026-09-01T00:00:00Z</published><updated>2026-09-01T00:00:00Z</updated>
        <arxiv:journal_ref>Test Journal 12 (2026)</arxiv:journal_ref>
        <arxiv:doi>10.1234/example</arxiv:doi><arxiv:comment>Accepted at Example Conference</arxiv:comment></entry></feed>'''
        papers, _ = Arxiv.parse(xml, datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(papers[0]["journal_ref"], "Test Journal 12 (2026)")
        self.assertEqual(papers[0]["doi"], "10.1234/example")
        self.assertEqual(papers[0]["publication_note"], "Accepted at Example Conference")

    def test_fulltext_metadata_survives_live_and_fresh_static_export(self):
        fixture = json.loads((ROOT / "tests/fixtures/paper-pipeline.json").read_text(encoding="utf-8"))
        config = validate_pipeline({"model": "claude/opus"})
        paper = {**fixture["papers"][0], "journal_ref": "Test Journal 12 (2026)", "doi": "10.1234/example"}
        path, document = assemble(paper, fixture["groups"], {}, [], config)
        self.assertEqual(validate_document(document, paper, fixture["markdown"], config), [])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic_write(root / "config.json", (ROOT / "config.json").read_text(encoding="utf-8"))
            atomic_write(root / path, document)
            garden = Garden(root)
            post = garden.posts()[0]
            app = create_app(garden)
            client = app.test_client()
            index = client.get("/").get_data(as_text=True)
            detail = client.get('/posts/' + post["id"]).get_data(as_text=True)
            site = export_site(app, garden)
            for html in (index, detail, (site / "index.html").read_text(encoding="utf-8"),
                         (site / "posts" / (post["id"] + ".html")).read_text(encoding="utf-8")):
                self.assertIn("Test Journal 12 (2026)", html)
                self.assertIn("claude/opus", html)
                self.assertIn(post["summary_date"], html)

    def test_publication_metadata_does_not_relax_unknown_fields(self):
        fixture = json.loads((ROOT / "tests/fixtures/paper-pipeline.json").read_text(encoding="utf-8"))
        config = validate_pipeline({})
        paper = {**fixture["papers"][0], "journal_ref": "Test Journal"}
        _, document = assemble(paper, fixture["groups"], {}, [], config)
        self.assertTrue(validate_document(document.replace('"journal_ref":', '"untrusted_field":'), paper, fixture["markdown"], config))
