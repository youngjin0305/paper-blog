from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import create_app, export_site, graph_script
from garden import ROOT, Garden, atomic_write
from paper_graph import build_graph, graph_papers, match_reference_rows, references_from_text, validate_graph_settings, sync_graph_evidence
from paper_queue import empty_queue, entry
from paper_pipeline import assemble, Pipeline
from paper_config import validate_pipeline


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        self.a = {"id": "arxiv:1901.00001", "source": "arxiv", "title": "Differential Analysis of a Small Block Cipher",
                  "authors": ["Fixture Author"], "abstract": "Differential cryptanalysis and key recovery on a block cipher Speck.",
                  "url": "https://arxiv.org/abs/1901.00001v1", "pdfUrl": "https://arxiv.org/pdf/1901.00001v1",
                  "published": "2019-01-01T00:00:00Z", "topic_id": "cryptanalysis", "doi": "10.0000/foundation",
                  "essential": True, "coreBasis": "Fixture foundation", "coreRationale": "Fixture selection, not a real paper.",
                  "evidence": [{"url": "https://arxiv.org/abs/1901.00001v1", "label": "Fixture"}],
                  "citation": {"count": 150, "source": "Crossref", "url": "https://api.crossref.org/works/fixture", "checkedAt": "2026-10-10"}}
        self.b = {**self.a, "id": "arxiv:2201.00002", "url": "https://arxiv.org/abs/2201.00002v1",
                  "pdfUrl": "https://arxiv.org/pdf/2201.00002v1", "published": "2022-01-01T00:00:00Z",
                  "title": "Neural Differential Analysis for Key Recovery on Speck", "topic_id": "ai-cryptanalysis",
                  "essential": False, "doi": "10.0000/followup"}
        self.queue = empty_queue(); self.queue["papers"] = [entry(self.a, "pinned"), entry(self.b)]
        self.queue["papers"][1].update(score=3.8, scoreDetail={"llm": {"relevance": {"score": 4}}})
        self.write()

    def write(self):
        atomic_write(self.root / "config.json", json.dumps(self.config))
        atomic_write(self.root / "data/core-papers.json", json.dumps({"version": 1, "papers": [self.a]}))
        atomic_write(self.root / "data/paper-queue.json", json.dumps(self.queue))

    def publish_fixture(self, paper):
        fixture = json.loads((ROOT / "tests/fixtures/paper-pipeline.json").read_text(encoding="utf-8"))
        path, doc = assemble(paper, fixture["groups"], {}, [], validate_pipeline(self.config["pipeline"]),
                             topic_ids={t["id"] for t in self.config["topics"]})
        atomic_write(self.root / path, doc)
        return path

    def test_citation_requires_doi_or_full_title_in_actual_references(self):
        self.assertEqual(references_from_text(self.b, self.a["title"] + " is discussed in the Introduction", [self.a], "2026-10-10"), [])
        text = "References\n[1] Author. Differential Analysis of a Small\nBlock Cipher. 2019."
        refs = references_from_text(self.b, text, [self.a], "2026-10-10")
        self.assertEqual(refs[0]["citedId"], self.a["id"])
        self.assertEqual(refs[0]["evidence"]["origin"], "original-references")
        self.assertEqual(references_from_text(self.b, "References\n[1] Differential Analysis", [self.a], "2026-10-10"), [])
        rows = [{"DOI": "10.0000/FOUNDATION", "article-title": "A different deposited title"}]
        refs = match_reference_rows(self.b, rows, [self.a], "https://api.crossref.org/works/fixture", "crossref-references", "2026-10-10")
        self.assertEqual(refs[0]["evidence"]["match"], "DOI")

    def test_similarity_is_labeled_inference_and_points_from_older_to_newer(self):
        garden = Garden(self.root)
        first = build_graph(self.root, garden.config(), garden.posts())
        self.assertEqual(first, build_graph(self.root, garden.config(), garden.posts()))
        self.assertEqual(first["edges"][0]["kind"], "related")
        self.assertEqual((first["edges"][0]["source"], first["edges"][0]["target"]), (self.a["id"], self.b["id"]))
        self.assertIn("실제 인용", first["edges"][0]["reason"])

    def test_citation_evidence_overrides_similarity_and_self_edges_are_ignored(self):
        evidence = {"url": "https://example.org/references", "match": "title", "origin": "original-references", "excerpt": "Fixture reference", "checkedAt": "2026-10-10"}
        self.queue["papers"][1]["graphReferences"] = [{"citedId": self.a["id"], "evidence": evidence}, {"citedId": self.b["id"], "evidence": evidence}]
        self.write()
        garden = Garden(self.root); graph = build_graph(self.root, garden.config(), garden.posts())
        self.assertEqual(len(graph["edges"]), 1)
        self.assertEqual(graph["edges"][0]["kind"], "citation")

    def test_unknown_dates_in_same_year_do_not_invent_temporal_order(self):
        self.a.update(published="1999-01-01T00:00:00Z", publicationYear=1999, publishedPrecision="year")
        self.queue["papers"][1].update(published="1999-01-01T00:00:00Z", publicationYear=1999, publishedPrecision="year")
        self.write(); garden = Garden(self.root)
        self.assertEqual(build_graph(self.root, garden.config(), garden.posts())["edges"], [])

    def test_same_year_order_compares_actual_instants_across_timezones(self):
        self.a["published"] = "2022-01-01T09:00:00+09:00"
        self.queue["papers"][1]["published"] = "2022-01-01T01:00:00Z"
        self.write(); garden = Garden(self.root)
        edges = build_graph(self.root, garden.config(), garden.posts())["edges"]
        self.assertEqual((edges[0]["source"], edges[0]["target"]), (self.a["id"], self.b["id"]))

    def test_quality_does_not_treat_archive_or_candidate_score_as_validation(self):
        self.queue["papers"][1]["journal_ref"] = "Cryptology ePrint Archive"
        self.write(); garden = Garden(self.root)
        node = build_graph(self.root, garden.config(), garden.posts())["nodes"][1]
        self.assertFalse(node["venueConfirmed"]); self.assertFalse(node["recommended"])
        self.publish_fixture(self.b)
        node = next(n for n in build_graph(self.root, garden.config(), garden.posts())["nodes"] if n["id"] == self.b["id"])
        self.assertTrue(node["summaryId"]); self.assertTrue(node["recommended"])
        self.queue["papers"][1]["scoreDetail"]["llm"]["relevance"]["score"] = 3
        self.write()
        node = next(n for n in build_graph(self.root, garden.config(), garden.posts())["nodes"] if n["id"] == self.b["id"])
        self.assertFalse(node["recommended"])

    def test_accepted_venue_and_scope_are_checked_independently(self):
        self.queue["papers"][1]["publication_note"] = "Accepted at CRYPTO 2022"
        self.write(); garden = Garden(self.root)
        node = next(n for n in build_graph(self.root, garden.config(), garden.posts())["nodes"] if n["id"] == self.b["id"])
        self.assertTrue(node["recommended"])
        self.queue["papers"][1].update(title="LLM security knowledge benchmark", abstract="A large language model benchmark of security knowledge.")
        self.write()
        node = next(n for n in build_graph(self.root, garden.config(), garden.posts())["nodes"] if n["id"] == self.b["id"])
        self.assertFalse(node["inScope"]); self.assertFalse(node["recommended"])

    def test_failed_noncore_and_demo_are_excluded_but_core_is_retained(self):
        self.queue["papers"][0]["status"] = "failed"; self.queue["papers"][1]["status"] = "expired"
        self.write(); garden = Garden(self.root); garden.seed_demo()
        nodes = build_graph(self.root, garden.config(), garden.posts())["nodes"]
        self.assertEqual([n["id"] for n in nodes], [self.a["id"]])

    def test_fresh_pages_export_uses_tracked_queue_evidence_without_network(self):
        self.publish_fixture(self.a)
        garden = Garden(self.root); app = create_app(garden); client = app.test_client()
        with patch("requests.get", side_effect=AssertionError("Export must not fetch metadata")):
            site = export_site(app, garden)
        self.assertIn("연구 흐름", (site / "research-flow.html").read_text(encoding="utf-8"))
        data = (site / "assets/research-graph-data.js").read_text(encoding="utf-8")
        self.assertIn('"summaryId":', data)
        self.assertTrue((site / "assets/research-graph.js").exists())
        self.assertEqual(client.get("/research-flow").status_code, 200)
        response = client.get("/research-flow/data.js")
        self.assertEqual(response.status_code, 200); self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertIn('href="/research-flow"', client.get("/").get_data(as_text=True))

    def test_safe_graph_serialization_and_configuration_validation(self):
        self.assertNotIn("</script>", graph_script({"title": "</script><img src=x>"}))
        self.assertIn("\\u003c", graph_script({"title": "<test>"}))
        for changed in ({"evidence_path": "../private.json"}, {"max_nodes": 0}, {"recommended_relevance": 9}, {"concepts": None}):
            with self.assertRaises(ValueError): validate_graph_settings(changed)
        garden = Garden(self.root); config = garden.config()
        config.pop("research_graph")
        self.assertIn("research_graph", garden.save_config(config))

    def test_evidence_sync_dry_run_does_not_write_and_keeps_reference_origin(self):
        class Response:
            def raise_for_status(self): pass
            def json(self): return {"message": {"reference": [{"DOI": self_a["doi"]}]}}
        self_a = self.a
        garden = Garden(self.root)
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with patch("requests.get", return_value=Response()), patch("paper_sources.Sources.download_pdf", side_effect=ValueError("No fixture PDF")):
            result = sync_graph_evidence(self.root, garden.config(), garden.posts(), dry_run=True)
        self.assertEqual(result["edges"][0]["evidence"]["origin"], "crossref-references")
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_daily_carries_new_reference_edges_in_the_published_queue(self):
        fixture = json.loads((ROOT / "tests/fixtures/paper-pipeline.json").read_text(encoding="utf-8"))
        fixture["papers"] = [deepcopy(self.b)]
        fixture["references"] = [1]
        fixture["markdown"] = fixture["markdown"].split("## References")[0] + "\n## References\n\n[1] " + self.a["title"]
        fixture["source_text"] = fixture["source_text"].split("References")[0] + "\nReferences\n[1] " + self.a["title"]
        with redirect_stdout(io.StringIO()):
            pipeline = Pipeline(self.root, dry_run=True, fixture=fixture)
            result = pipeline.daily(paper_id=self.b["id"])
        self.assertTrue(result["valid"], result["errors"])
        paper = next(p for p in pipeline.queue["papers"] if p["id"] == self.b["id"])
        self.assertEqual(paper["graphReferences"][0]["citedId"], self.a["id"])
        self.assertEqual(paper["status"], "done")


if __name__ == "__main__":
    unittest.main()
