from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
import io
from unittest.mock import patch

from app import create_app, export_site
from garden import ROOT, Garden, atomic_write, grouped_topics, validate_config
from paper_catalog import annotate_posts, load_catalog, reading_library, seed_core
from paper_pipeline import Pipeline, FixtureBackend, assemble
from paper_queue import empty_queue, entry, ordered, merge_weekly
from paper_sources import rule_score, Sources
from paper_config import validate_pipeline


FIXTURE = json.loads((ROOT / "tests/fixtures/paper-pipeline.json").read_text(encoding="utf-8"))
STAMP = "2026-10-09T12:00:00+00:00"


def core_paper(identifier="2609.00001", topic="ai-cryptanalysis"):
    return {**FIXTURE["papers"][0], "id": "arxiv:" + identifier, "source": "arxiv",
            "url": "https://arxiv.org/abs/" + identifier, "pdfUrl": "https://arxiv.org/pdf/" + identifier,
            "topic_id": topic, "essential": True, "coreRationale": "검증된 기반 연구를 위한 테스트 자료.",
            "coreBasis": "원전", "evidence": [{"url": "https://arxiv.org/abs/" + identifier, "label": "원문"}],
            "citation": {"count": 125, "source": "Crossref", "checkedAt": "2026-10-09",
                         "url": "https://api.crossref.org/works/test"}}


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        atomic_write(self.root / "config.json", json.dumps(self.raw))
        self.paper = core_paper()
        self.catalog = {"version": 1, "criteria": "원전과 검증된 인용 기록", "papers": [self.paper]}
        self.save_catalog()

    def save_catalog(self):
        atomic_write(self.root / "data/core-papers.json", json.dumps(self.catalog, ensure_ascii=False))

    def test_reset_keeps_seen_and_done_but_retires_all_old_pending(self):
        queue = empty_queue()
        for state in ("candidate", "pinned", "failed", "done"):
            paper = entry(core_paper("2609.0000" + str(len(queue["papers"]) + 2)), state, STAMP)
            queue["papers"].append(paper)
            queue["seen"].append(paper["id"])
        seen = set(queue["seen"])
        seed_core(queue, [self.paper], STAMP, reset_pending=True)
        self.assertEqual([p["status"] for p in queue["papers"][:4]], ["expired", "expired", "expired", "done"])
        self.assertTrue(seen <= set(queue["seen"]))
        self.assertEqual([p["id"] for p in ordered(queue)], [self.paper["id"]])
        merge_weekly(queue, [entry(self.paper)], {"pool_limit": 1, "expiry_weeks": 1}, "2026-10-12T00:00:00+00:00")
        self.assertEqual(ordered(queue)[0]["status"], "pinned")
        self.assertEqual(len({p["id"] for p in queue["papers"]}), len(queue["papers"]))

    def test_seed_is_idempotent_and_never_requeues_a_completed_core_paper(self):
        queue = empty_queue()
        seed_core(queue, [self.paper], STAMP)
        first = deepcopy(queue)
        seed_core(queue, [self.paper], "2026-10-10T00:00:00+00:00")
        self.assertEqual(queue, first)
        queue["papers"][0].update(status="done", postPath="content/review.md")
        seed_core(queue, [self.paper], STAMP, reset_pending=True)
        self.assertEqual(queue["papers"][0]["status"], "done")
        self.assertEqual(queue["papers"][0]["postPath"], "content/review.md")
        self.assertEqual(ordered(queue), [])

    def test_catalog_rejects_duplicate_ids_and_unverified_metadata(self):
        for mutate in (
            lambda c: c["papers"].append(deepcopy(c["papers"][0])),
            lambda c: c["papers"][0].update(authors=[]),
            lambda c: c["papers"][0].update(authors="Author"),
            lambda c: c["papers"][0].update(pdfUrl="https://127.0.0.1/private.pdf"),
            lambda c: c["papers"][0].update(evidence=[]),
            lambda c: c["papers"][0].update(citation={"count": 125}),
        ):
            self.catalog = {"version": 1, "papers": [deepcopy(self.paper)]}
            mutate(self.catalog)
            self.save_catalog()
            with self.assertRaises(ValueError):
                load_catalog(self.root, {})

    def test_seed_dry_run_does_not_write_and_disabled_collection_can_be_pinned(self):
        self.catalog["papers"][0]["topic_id"] = "ai-digital-forensics"
        self.save_catalog()
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with redirect_stdout(io.StringIO()):
            pipeline = Pipeline(self.root, dry_run=True, backend=FixtureBackend(FIXTURE))
            pipeline.seed_core(reset_pending=True)
        self.assertEqual(pipeline.queue["papers"][0]["status"], "pinned")
        self.assertEqual(pipeline.queue["papers"][0]["topic_id"], "ai-digital-forensics")
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_live_and_static_essentials_keep_completed_papers_with_summary_links(self):
        second = core_paper("2609.00002", "cryptanalysis")
        second["title"] = "Second core paper"
        self.catalog["papers"].append(second)
        self.save_catalog()
        queue = empty_queue()
        seed_core(queue, self.catalog["papers"], STAMP)
        config = validate_pipeline(self.raw["pipeline"])
        path, document = assemble(self.paper, FIXTURE["groups"], {}, [], config,
                                  topic_ids={t["id"] for t in self.raw["topics"]})
        atomic_write(self.root / path, document)
        queue["papers"][0].update(status="done", postPath=path)
        atomic_write(self.root / "data/paper-queue.json", json.dumps(queue))
        garden = Garden(self.root)
        app = create_app(garden)
        client = app.test_client()
        essential_html = client.get("/essentials").get_data(as_text=True)
        self.assertIn("정리 글 읽기", essential_html)
        self.assertIn("Second core paper", essential_html)
        self.assertNotIn(self.paper["title"], client.get("/reading-list").get_data(as_text=True))
        filtered = client.get("/essentials?category=cryptanalysis&q=Second").get_data(as_text=True)
        self.assertIn("Second core paper", filtered)
        self.assertNotIn(self.paper["title"], filtered)
        self.assertEqual(client.get("/essentials?category=missing").status_code, 404)
        site = export_site(app, garden)
        html = (site / "essentials.html").read_text(encoding="utf-8")
        self.assertIn('href="posts/', html)
        self.assertIn("Crossref 인용 125회", html)
        self.assertIn("Cryptography", html)
        self.assertIn("Digital Forensics", html)
        self.assertIn("reading:arxiv:2609.00002", (site / "assets/search-data.js").read_text(encoding="utf-8"))
        # A different arXiv version is still the same essential paper.
        posts = [{"source": json.dumps({"url": self.paper["url"] + "v2"})}]
        self.assertTrue(annotate_posts(posts, self.catalog)[0]["essential"])

    def test_category_groups_survive_config_round_trip(self):
        config = validate_config(self.raw)
        groups = grouped_topics(config["topics"])
        self.assertEqual([g["name"] for g in groups], ["Cryptography", "Digital Forensics"])
        self.assertFalse(next(t for t in config["topics"] if t["id"] == "ai-digital-forensics")["enabled"])

    def test_collection_focus_rejects_general_llm_security_and_routes_attacks(self):
        config = validate_pipeline(self.raw["pipeline"])
        def classify(abstract):
            return rule_score({"title": "Research", "abstract": abstract, "categories": ["cs.CR"]}, config)
        self.assertEqual(classify("LLM benchmark for cryptographic engineering security")[0], 0)
        self.assertEqual(classify("Privacy leakage in neural network inference")[0], 0)
        self.assertEqual(classify("Neural differential cryptanalysis with a key recovery attack on Speck")[1]["topic"], "ai-cryptanalysis")
        self.assertEqual(classify("Boomerang attack and key recovery on a block cipher AES")[1]["topic"], "cryptanalysis")
        self.assertEqual(classify("Deep learning side-channel key recovery on AES")[0], 0)

    def test_collection_query_enforces_exclusions_before_fetching(self):
        config = {**validate_pipeline(self.raw["pipeline"]), "use_eprint": False}
        source = Sources(config)
        with patch.object(source, "arxiv", return_value=([], 0)) as fetch:
            self.assertEqual(source.recent(), [])
        query = fetch.call_args.args[0]["search_query"]
        self.assertIn('ANDNOT (all:"neural"', query)
        self.assertIn('all:"neural distinguisher"', query)
        self.assertNotIn("deepfake", query)

    def test_summary_prompt_uses_citation_not_selection_annotations(self):
        pipeline = Pipeline(self.root, dry_run=True, backend=FixtureBackend(FIXTURE))
        paper = {**self.paper, "note": "editorial-only-note"}
        with patch.object(pipeline.backend, "generate", return_value="fixture response") as generate:
            pipeline.group("B", paper, "Original paper text")
        prompt = generate.call_args.args[0]
        self.assertIn(paper["title"], prompt)
        self.assertNotIn(paper["coreRationale"], prompt)
        self.assertNotIn("editorial-only-note", prompt)
        self.assertNotIn('"citation"', prompt)


if __name__ == "__main__":
    unittest.main()
