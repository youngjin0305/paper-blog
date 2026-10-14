"""Publisher recovery tests use tiny generated PDFs and no external requests."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pymupdf
import requests

from paper_config import validate_pipeline
from paper_sources import Sources


def http_error(status):
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(response=response)


class PublisherDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.logs = []
        self.source = Sources(validate_pipeline({}), root=self.root, log=self.logs.append)
        self.paper = {"id": "eprint:2026/123", "title": "Example Paper", "authors": ["Alice Author", "Bob Writer"],
                      "doi": "10.1234/example", "pdfUrl": "https://eprint.iacr.org/2026/123.pdf"}
        self.url = "https://publisher.example/content/pdf/example"
        self.record = {"title": [self.paper["title"]], "author": [{"given": "Alice", "family": "Author"},
                       {"given": "Bob", "family": "Writer"}], "link": [{"URL": self.url}]}
        self.pdf = self.make_pdf()

    def make_pdf(self, title="Example Paper", authors="Alice Author and Bob Writer"):
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((72, 72), title + "\n" + authors + "\nFixture body. Accuracy 82.5 percent.")
            return pdf.tobytes()

    def test_blocked_source_recovers_and_reuses_verified_cache(self):
        with patch.object(self.source, "get", return_value=SimpleNamespace(json=lambda: dict(message=self.record))), \
             patch.object(self.source, "download_pdf", side_effect=[http_error(403), self.pdf]) as download:
            self.assertEqual(self.source.paper_pdf(self.paper), self.pdf)
        self.assertEqual(download.call_count, 2)
        self.assertEqual(self.paper["pdfUrl"], self.url)
        manifest = next(self.root.rglob("publisher-pdf.json"))
        self.assertEqual(json.loads(manifest.read_text())["url"], self.url)
        with patch.object(self.source, "get", side_effect=AssertionError("No network on cache hit")), \
             patch.object(self.source, "download_pdf", side_effect=AssertionError("No download on cache hit")):
            self.assertEqual(self.source.paper_pdf(self.paper), self.pdf)
        self.assertTrue(any("HTTP 403" in line for line in self.logs))
        self.assertTrue(any("cached" in line for line in self.logs))

    def test_publisher_landing_page_uses_verified_citation_pdf_link(self):
        record = {**self.record, "link": None, "resource": {"primary": {"URL": "https://journal.example/article"}}}
        html = ('<meta name="citation_title" content="Example Paper">'
                '<meta name="citation_doi" content="10.1234/example">'
                '<meta name="citation_pdf_url" content="https://journal.example/article/pdf">')
        with patch.object(self.source, "get", side_effect=[SimpleNamespace(json=lambda: dict(message=record)), SimpleNamespace(text=html)]), \
             patch.object(self.source, "download_pdf", side_effect=[http_error(403), self.pdf]):
            self.assertEqual(self.source.paper_pdf(self.paper), self.pdf)
        self.assertEqual(self.paper["pdfUrl"], "https://journal.example/article/pdf")

    def test_mismatched_doi_metadata_never_downloads_the_alternate(self):
        for changes in ({"title": ["Another paper"]}, {"author": [{"given": "Another", "family": "Author"}]}):
            with self.subTest(changes=changes), patch.object(self.source, "get", return_value=SimpleNamespace(json=lambda: dict(message={**self.record, **changes}))), \
                 patch.object(self.source, "download_pdf", side_effect=http_error(403)) as download:
                with self.assertRaisesRegex(ValueError, "do(?:es)? not match"):
                    self.source.paper_pdf(deepcopy(self.paper))
                self.assertEqual(download.call_count, 1)

    def test_mismatched_pdf_content_is_not_cached_or_accepted(self):
        for bad in (self.make_pdf(title="Other paper"), self.make_pdf(authors="Different Author")):
            with self.subTest(), patch.object(self.source, "get", return_value=SimpleNamespace(json=lambda: dict(message=self.record))), \
                 patch.object(self.source, "download_pdf", side_effect=[http_error(403), bad]):
                with self.assertRaisesRegex(ValueError, "do not match|does not match"):
                    self.source.paper_pdf(deepcopy(self.paper))
        self.assertEqual(list(self.root.rglob("publisher-pdf.json")), [])

    def test_429_stops_without_publisher_lookup_or_retry(self):
        paper = {**self.paper, "pdfUrl": "https://eprint.iacr.org/paper.pdf?token=private-value"}
        with patch.object(self.source, "get", side_effect=AssertionError("Must not retry 429")), \
             patch.object(self.source, "download_pdf", side_effect=http_error(429)) as download:
            with self.assertRaisesRegex(RuntimeError, "HTTP 429") as error:
                self.source.paper_pdf(paper)
        self.assertEqual(download.call_count, 1)
        self.assertNotIn("private-value", str(error.exception) + " ".join(self.logs))

    def test_alternate_lookup_429_stops_without_another_download(self):
        with patch.object(self.source, "get", side_effect=http_error(429)) as get, \
             patch.object(self.source, "download_pdf", side_effect=http_error(403)) as download:
            with self.assertRaisesRegex(RuntimeError, "HTTP 429"):
                self.source.paper_pdf(self.paper)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(download.call_count, 1)

    def test_fallback_can_be_disabled_and_private_links_are_rejected(self):
        self.source.config["publisher_fallback"] = False
        with patch.object(self.source, "download_pdf", side_effect=http_error(403)), \
             patch.object(self.source, "publisher_pdf", side_effect=AssertionError("Disabled")):
            with self.assertRaisesRegex(RuntimeError, "no publisher fallback"):
                self.source.paper_pdf(self.paper)
        self.source.config["publisher_fallback"] = True
        record = {**self.record, "link": [{"URL": "https://127.0.0.1/content/pdf/private"}]}
        with patch.object(self.source, "get", return_value=SimpleNamespace(json=lambda: dict(message=record))), \
             patch.object(self.source, "download_pdf", side_effect=http_error(403)) as download:
            with self.assertRaisesRegex(ValueError, "no verified public PDF"):
                self.source.paper_pdf(self.paper)
        self.assertEqual(download.call_count, 1)

    def test_no_write_mode_does_not_create_a_cache(self):
        self.source.cache_writes = False
        with patch.object(self.source, "get", return_value=SimpleNamespace(json=lambda: dict(message=self.record))), \
             patch.object(self.source, "download_pdf", side_effect=[http_error(403), self.pdf]):
            self.assertEqual(self.source.paper_pdf(self.paper), self.pdf)
        self.assertEqual(list(self.root.rglob("*")), [])

    def test_cache_checksum_is_checked(self):
        with patch.object(self.source, "get", return_value=SimpleNamespace(json=lambda: dict(message=self.record))), \
             patch.object(self.source, "download_pdf", side_effect=[http_error(403), self.pdf]):
            self.source.paper_pdf(self.paper)
        next(self.root.rglob("publisher.pdf")).write_bytes(self.pdf + b"\n% changed cache bytes\n")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.source.paper_pdf(self.paper)
