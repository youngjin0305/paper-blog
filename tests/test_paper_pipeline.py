from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from app import create_app, export_site
from garden import Garden, ROOT, atomic_write
from paper_config import validate_pipeline
from paper_git import Publisher
from paper_llm import AgyBackend, QuotaExceeded, AgyPermissionError, configure_workspace
from paper_pipeline import Pipeline, FixtureBackend, assemble
from paper_queue import canonical_id, empty_queue, entry, merge_weekly, ordered, pin, weekly_completed
from paper_sources import Sources, identify, parse_eprint_feed, rule_score, keyword_matches
from paper_validation import parse_rank, parse_references, numbers, validate_document, validate_group


FIXTURE = json.loads((ROOT / "tests/fixtures/paper-pipeline.json").read_text(encoding="utf-8"))
CONFIG = validate_pipeline({"rank_batch_size": 1})
PAPER = FIXTURE["papers"][0]
STAMP = "2026-09-22T00:00:00+00:00"


class QueueTests(unittest.TestCase):
    def item(self, identifier, score=0, weeks=0):
        paper = entry({**PAPER, "id": identifier}, timestamp=STAMP)
        paper.update(score=score, weeksInQueue=weeks)
        return paper

    def test_rerank_expiry_cap_and_pinned_exemption(self):
        queue = empty_queue()
        queue["papers"] = [self.item("old", 5, 3), self.item("low", 1), self.item("middle", 3)]
        pinned = pin(queue, {**PAPER, "id": "pin"})
        pinned["weeksInQueue"] = 100
        config = {**CONFIG, "pool_limit": 2}
        merge_weekly(queue, [self.item("new", 4)], config, STAMP)
        self.assertEqual([p["id"] for p in ordered(queue)], ["arxiv:pin", "arxiv:new", "arxiv:middle"])
        self.assertEqual(queue["papers"][0]["status"], "expired")
        self.assertEqual(queue["papers"][1]["status"], "expired")
        self.assertEqual(pinned["weeksInQueue"], 100)
        self.assertEqual(ordered(queue)[1]["weeksInQueue"], 1)

    def test_seen_prevents_expired_reentry_and_version_duplicates(self):
        queue = empty_queue()
        queue["seen"] = ["arxiv:2609.00001"]
        item = self.item("2609.00001v3", 5)
        merge_weekly(queue, [item, item], CONFIG, STAMP)
        self.assertEqual(queue["papers"], [])
        self.assertEqual(canonical_id("arxiv:2609.00001v4", "arxiv"), item["id"])

    def test_fifo_and_promotion_preserve_timestamp(self):
        queue = empty_queue()
        old = self.item("old", 1)
        queue["papers"].append(old)
        new = pin(queue, {**PAPER, "id": "new"})
        new["addedAt"] = "2026-09-23T00:00:00+00:00"
        pin(queue, old, "priority")
        self.assertEqual(ordered(queue)[0]["id"], old["id"])
        self.assertEqual(old["addedAt"], STAMP)
        self.assertEqual(old["note"], "priority")

    def test_weekly_idempotence(self):
        queue = empty_queue()
        merge_weekly(queue, [self.item("new", 4)], CONFIG, STAMP)
        before = deepcopy(queue)
        self.assertFalse(merge_weekly(queue, [], CONFIG, STAMP))
        self.assertEqual(queue, before)

    def test_manual_tuesday_setup_does_not_skip_next_monday(self):
        queue = empty_queue()
        queue["lastWeeklyAt"] = "2026-09-22T12:00:00+09:00"
        self.assertFalse(weekly_completed(queue, "2026-09-28T12:00:00+09:00"))


class ValidationTests(unittest.TestCase):
    def document(self, groups=None):
        return assemble(PAPER, groups or FIXTURE["groups"], {}, [], CONFIG)[1]

    def test_valid_required_sections_and_optional_omission(self):
        groups = deepcopy(FIXTURE["groups"])
        groups["D"] = "## 결론\n원문의 결론이다."
        self.assertEqual(validate_document(self.document(groups), PAPER, FIXTURE["markdown"], CONFIG), [])

    def test_missing_required_and_short_sections(self):
        groups = deepcopy(FIXTURE["groups"])
        groups["A"] = "## 주요 기여\n기여만 있음"
        groups["B"] = "## 제시한 방법론\n짧음"
        errors = validate_document(self.document(groups), PAPER, FIXTURE["markdown"], CONFIG)
        self.assertTrue(any("문제 정의" in e for e in errors))
        self.assertTrue(any("characters" in e for e in errors))

    def test_numeric_normalization_and_hallucination_report(self):
        self.assertEqual(numbers("1,000 82.50 % -0.50"), numbers("1000 82.5% -0.5"))
        self.assertEqual(numbers("1 000"), numbers("1,000"))
        errors = validate_group("C", FIXTURE["groups"]["C"] + "\n없는 수치 99.99%", FIXTURE["markdown"], CONFIG)
        self.assertTrue(any("99.99" in e for e in errors))
        self.assertNotEqual(numbers("12"), numbers("112"))
        self.assertEqual(numbers("Batch size 16."), {"16"})
        self.assertEqual(numbers("정확도99.99%, GPT-4, 82 . 5"), {"99.99", "-4", "82.5"})

    def test_long_verbatim_source_copy_rejected(self):
        source = " ".join("word" + str(i) for i in range(30))
        errors = validate_group("A", "## 문제 정의\n" + source + "\n## 주요 기여\n기여", source, CONFIG)
        self.assertTrue(any("Verbatim" in error for error in errors))

    def test_links_and_frontmatter_must_match(self):
        document = self.document().replace(f"[원문]({PAPER['url']})", "원문")
        self.assertIn("Missing original/PDF link in body", validate_document(document, PAPER, FIXTURE["markdown"], CONFIG))
        document = self.document().replace('"source": "https://arxiv.org', '"source": "https://invalid.org')
        self.assertIn("Frontmatter source link mismatch", validate_document(document, PAPER, FIXTURE["markdown"], CONFIG))
        self.assertTrue(validate_document(self.document().replace('"basis":', '"unknown":'), PAPER, FIXTURE["markdown"], CONFIG))

    def test_fenced_headers_and_images_cannot_pass(self):
        self.assertTrue(validate_group("B", "```markdown\n## 제시한 방법론\n```", "", CONFIG))
        self.assertTrue(validate_group("B", FIXTURE["groups"]["B"] + "\n![figure](x.png)", "", CONFIG))

    def test_reference_verbatim_multiline_appendix_and_missing(self):
        refs = parse_references(FIXTURE["markdown"])
        self.assertEqual(refs, {1: "A. Author. Exact Retrieval.\n2024.", 2: "B. Author. Evaluation Design. 2025."})
        self.assertEqual(parse_references("No references in this text"), {})
        self.assertEqual(parse_references("References\n1. First.\n2. Second."), {1: "First.", 2: "Second."})
        self.assertEqual(parse_references("References\n[1] One\n[1] Another"), {})
        self.assertEqual(parse_references("**References**\n1. Original entry.\n\n## **Supplementary Material**\n1. An experiment, not a citation."), {1: "Original entry."})
        refs = parse_references("References\n1. Author. Conference,\n2025. pp. 1-4.\n2. Another author.\n## Appendix\n1. Experiment")
        self.assertEqual(refs, {1: "Author. Conference,\n2025. pp. 1-4.", 2: "Another author."})

    def test_rubric_schema_rejects_missing_and_out_of_range(self):
        self.assertEqual(parse_rank(json.dumps(FIXTURE["rank"])), FIXTURE["rank"])
        from jsonschema import ValidationError
        invalid = deepcopy(FIXTURE["rank"])
        invalid["novelty"]["score"] = 6
        with self.assertRaises(ValidationError):
            parse_rank(json.dumps(invalid))
        invalid["novelty"]["score"] = True
        with self.assertRaises(ValidationError):
            parse_rank(json.dumps(invalid))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copy(ROOT / "config.json", self.root / "config.json")
        config = json.loads((self.root / "config.json").read_text(encoding="utf-8"))
        config["topics"][0]["id"] = "ai"
        config["pipeline"] = deepcopy(CONFIG)
        (self.root / "config.json").write_text(json.dumps(config), encoding="utf-8")
        self.pipeline = Pipeline(self.root, dry_run=True, fixture=deepcopy(FIXTURE))
        self.output = io.StringIO()
        self.redirect = redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def test_all_dry_commands_no_writes(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.pipeline.weekly()
        self.pipeline.add("2609.00001v2", "fixture")
        self.assertTrue(self.pipeline.list())
        self.assertTrue(self.pipeline.daily()["valid"])
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_only_failed_group_regenerated_once(self):
        pin(self.pipeline.queue, PAPER)
        backend = self.pipeline.backend
        calls = []
        def generate(prompt, options):
            kind = options["kind"]
            calls.append(kind)
            if kind == "C" and calls.count("C") == 1:
                return FIXTURE["groups"]["C"] + "\nUnknown result 9999.99%"
            if kind == "C":
                self.assertIn("9999.99", prompt)
            return backend.generate(prompt, options)
        with patch.object(self.pipeline.backend, "generate", side_effect=generate):
            # Keep original method to avoid recursively invoking the mock.
            backend = FixtureBackend(FIXTURE)
            result = self.pipeline.daily()
        self.assertTrue(result["valid"])
        self.assertEqual(calls, ["A", "B", "C", "C", "D", "references"])

    def test_failed_draft_and_report_never_publish(self):
        self.pipeline.dry_run = False
        self.pipeline.fixture["groups"]["C"] += "\nAbsent number 9999.99%"
        pin(self.pipeline.queue, PAPER)
        with patch.object(self.pipeline.publisher, "preflight"), patch.object(self.pipeline.publisher, "prepare") as publish:
            result = self.pipeline.daily()
        self.assertFalse(result["valid"])
        publish.assert_not_called()
        self.assertFalse((self.root / "content").exists())
        self.assertEqual(len(list((self.root / "drafts").glob("*.validation.json"))), 1)
        item = self.pipeline.queue["papers"][0]
        self.assertEqual((item["status"], item["failCount"]), ("failed", 1))
        self.assertTrue(list((self.root / "data/papers").rglob("source.txt")))

    def test_resume_draft_revalidates_and_regenerates_only_invalid_group(self):
        pin(self.pipeline.queue, PAPER)
        groups = {**FIXTURE["groups"], "C": FIXTURE["groups"]["C"] + "\nAbsent 9999.99%"}
        path, document = assemble(PAPER, groups, {}, [], CONFIG)
        atomic_write(self.root / "drafts" / Path(path).name, document)
        backend = FixtureBackend(FIXTURE)
        with patch.object(self.pipeline.backend, "generate", side_effect=backend.generate) as generate:
            self.assertTrue(self.pipeline.daily(resume_draft=True)["valid"])
        self.assertEqual([call.args[1]["kind"] for call in generate.call_args_list], ["C", "references"])

    def test_quota_stops_without_retry_or_queue_changes(self):
        pin(self.pipeline.queue, PAPER)
        before = deepcopy(self.pipeline.queue)
        with patch.object(self.pipeline.backend, "generate", side_effect=QuotaExceeded("429")) as generate:
            with self.assertRaises(QuotaExceeded):
                self.pipeline.daily()
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(self.pipeline.queue, before)

    def test_empty_queue_success(self):
        self.assertIsNone(self.pipeline.daily())

    def test_weekly_rubric_retry_once_and_quota_abort(self):
        with patch.object(self.pipeline.backend, "generate", side_effect=["not JSON", json.dumps(FIXTURE["rank"])]) as generate:
            self.pipeline.weekly()
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(len(ordered(self.pipeline.queue)), 1)
        self.pipeline.queue = empty_queue()
        with patch.object(self.pipeline.backend, "generate", side_effect=QuotaExceeded("RESOURCE_EXHAUSTED")) as generate:
            with self.assertRaises(QuotaExceeded):
                self.pipeline.weekly()
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(self.pipeline.queue, empty_queue())

    def test_completed_ranks_survive_mid_weekly_service_failure(self):
        self.pipeline.dry_run = False
        self.pipeline.fixture["papers"].append({**PAPER, "id": "arxiv:2609.00002"})
        with patch.object(self.pipeline.backend, "generate", side_effect=[json.dumps(FIXTURE["rank"]), RuntimeError("service unavailable")]):
            with self.assertRaises(RuntimeError):
                self.pipeline.weekly()
        cache = json.loads((self.root / "data/paper-rank-cache.json").read_text(encoding="utf-8"))
        self.assertIn(PAPER["id"], cache)
        self.assertEqual(self.pipeline.queue, empty_queue())
        with patch.object(self.pipeline.backend, "generate", return_value=json.dumps(FIXTURE["rank"])) as generate:
            self.pipeline.weekly()
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(len(ordered(self.pipeline.queue)), 2)

    def test_batch_keeps_valid_paper_and_retries_only_invalid_paper(self):
        self.pipeline.config["rank_batch_size"] = 5
        other = "arxiv:2609.00002"
        self.pipeline.fixture["papers"].append({**PAPER, "id": other})
        payload = json.dumps({PAPER["id"]: FIXTURE["rank"], other: {"invalid": True}})
        with patch.object(self.pipeline.backend, "generate", side_effect=[payload, json.dumps(FIXTURE["rank"])]) as generate:
            self.pipeline.weekly()
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(generate.call_args_list[0].args[1]["kind"], "rank_batch")
        self.assertEqual(generate.call_args_list[1].args[1]["kind"], "rank")
        self.assertEqual(len(ordered(self.pipeline.queue)), 2)

    def test_low_relevance_candidate_is_excluded_but_manual_pin_is_kept(self):
        rank = deepcopy(FIXTURE["rank"])
        rank["relevance"]["score"] = 2
        with patch.object(self.pipeline.backend, "generate", return_value=json.dumps(rank)):
            self.pipeline.weekly()
        self.assertEqual(ordered(self.pipeline.queue), [])
        paper = pin(self.pipeline.queue, PAPER)
        paper["scoreDetail"] = {"llm": rank}
        self.pipeline.apply_topic_gate()
        self.assertEqual(paper["status"], "pinned")

    def test_frontmatter_posts_visible_without_db_registration(self):
        path, document = assemble(PAPER, FIXTURE["groups"], {}, [], CONFIG)
        atomic_write(self.root / path, document)
        garden = Garden(self.root)
        self.assertEqual(garden.posts()[0]["basis"], "fulltext")
        app = create_app(garden)
        site = export_site(app, garden)
        self.assertIn(PAPER["title"], (site / "index.html").read_text(encoding="utf-8"))
        self.assertIn("FULL PAPER REVIEW", (site / "posts" / (garden.posts()[0]["id"] + ".html")).read_text(encoding="utf-8"))

    def test_blog_settings_save_preserves_pipeline(self):
        garden = Garden(self.root)
        before = garden.config()["pipeline"]
        config = garden.config()
        config.pop("pipeline")
        garden.save_config(config)
        self.assertEqual(garden.config()["pipeline"], before)

    def test_cli_offline_commands_leave_workspace_unchanged(self):
        for path in ROOT.glob("*.py"):
            shutil.copy(path, self.root / path.name)
        fixture = self.root / "tests/fixtures/paper-pipeline.json"
        fixture.parent.mkdir(parents=True)
        fixture.write_text(json.dumps(FIXTURE), encoding="utf-8")
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        for command in (["weekly"], ["daily"], ["add", "2609.00001"], ["list"]):
            result = subprocess.run([sys.executable, "-B", "paper_pipeline.py", *command, "--dry-run", "--fixture", str(fixture)],
                                    cwd=self.root, capture_output=True, encoding="utf-8", timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


class SourceTests(unittest.TestCase):
    def test_eprint_uses_full_article_date_over_citation_year(self):
        html = '<meta name="citation_title" content="Title"><meta property="og:description" content="Abstract"><meta name="citation_publication_date" content="2026"><meta property="article:published_time" content="2026-09-18T13:05:43+00:00">'
        from types import SimpleNamespace
        with patch.object(Sources, "get", return_value=SimpleNamespace(text=html)):
            paper = Sources(CONFIG).metadata("https://eprint.iacr.org/2026/2092")
        self.assertEqual(paper["published"], "2026-09-18T13:05:43+00:00")

    def test_url_normalization(self):
        self.assertEqual(identify("https://arxiv.org/pdf/2609.00001v2.pdf"), ("arxiv", "arxiv:2609.00001"))
        self.assertEqual(identify("https://eprint.iacr.org/2026/10.pdf"), ("eprint", "eprint:2026/10"))
        self.assertEqual(identify("https://example.org/paper.pdf")[0], "manual")

    def test_rss2_and_rdf_dates(self):
        for xml in (
            '<rss><channel><item><title>T</title><link>https://eprint.iacr.org/2026/1</link><pubDate>Mon, 21 Sep 2026 00:00:00 GMT</pubDate><description>Abstract</description></item></channel></rss>',
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/"><item><title>T</title><link>https://eprint.iacr.org/2026/1</link><dc:date>2026-09-21T00:00:00Z</dc:date><description>Abstract</description></item></rdf:RDF>'
        ):
            paper = parse_eprint_feed(xml)[0]
            self.assertEqual(paper["id"], "eprint:2026/1")
            self.assertEqual(paper["published"], "2026-09-21T00:00:00+00:00")

    def test_real_pdf_conversion_without_image_files(self):
        import pymupdf
        with pymupdf.open() as pdf:
            page = pdf.new_page()
            page.insert_text((72, 72), "Fixture paper. Accuracy 82.5 percent. Batch size 16.")
            data = pdf.tobytes()
        source = Sources(CONFIG)
        with patch.object(source, "download_pdf", return_value=data):
            markdown, text = source.fulltext(PAPER)
        self.assertIn("82.5", markdown)
        self.assertIn("82.5", text)
        self.assertNotIn("![", markdown)


class AgyTests(unittest.TestCase):
    def process(self, command, **kwargs):
        self.command, self.kwargs = command, kwargs
        self.work = Path(kwargs["cwd"])
        self.assertIn("fixture prompt", (self.work / "prompt.txt").read_text(encoding="utf-8"))
        if self.answer is not None:
            (self.work / "result.txt").write_text(self.answer, encoding="utf-8")
        if getattr(self, "internal_log", None):
            (self.work / "agy.log").write_text(self.internal_log, encoding="utf-8")
        from unittest.mock import Mock
        process = Mock()
        process.stdout = io.BytesIO(self.stdout)
        process.stderr = io.BytesIO(self.stderr)
        process.poll.return_value = None if self.running else 0
        process.returncode = 0
        return process

    def setUp(self):
        self.answer, self.stdout, self.stderr, self.running = "file answer", b"", b"", False
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cli = AgyBackend({**CONFIG, "agy_work_dir": self.temp.name})

    def invoke(self):
        with patch("paper_llm.shutil.which", return_value="agy.exe"), patch("paper_llm.subprocess.Popen", side_effect=self.process):
            return self.cli.generate("fixture prompt")

    def test_empty_stdout_uses_file_and_no_shell(self):
        self.assertEqual(self.invoke(), "file answer")
        self.assertFalse(self.kwargs["shell"])
        self.assertIn("--sandbox", self.command)
        self.assertIn("--print-timeout", self.command)
        self.assertNotIn("--dangerously-skip-permissions", self.command)
        self.assertFalse(self.work.exists())

    def test_stdout_is_never_a_fallback(self):
        self.answer, self.stdout = None, b"unverified stdout answer"
        with self.assertRaisesRegex(RuntimeError, "did not create"):
            self.invoke()

    def test_legitimate_429_experiment_value_is_not_quota(self):
        self.answer = "## 실험 및 평가\n문서 429개를 사용했다."
        self.assertEqual(self.invoke(), self.answer)

    def test_quota_terminates_process_without_retry(self):
        self.running, self.stderr = True, b"RESOURCE_EXHAUSTED: HTTP 429"
        with patch("paper_llm.stop_process") as stop:
            with self.assertRaises(QuotaExceeded):
                self.invoke()
        stop.assert_called_once()

    def test_timeout_terminates_process(self):
        self.running = True
        self.cli.config = {**self.cli.config, "timeout": 0.02}
        with patch("paper_llm.stop_process") as stop:
            with self.assertRaises(TimeoutError):
                self.invoke()
        stop.assert_called_once()

    def test_internal_log_quota_stops_even_with_output_file_and_empty_pipes(self):
        self.running = True
        self.internal_log = "Run: attempt 1 failed (RESOURCE_EXHAUSTED (code 429): Individual quota reached), retrying in 4s"
        with patch("paper_llm.stop_process") as stop:
            with self.assertRaises(QuotaExceeded):
                self.invoke()
        stop.assert_called_once()
        self.assertIn("--log-file", self.command)

    def test_completed_process_log_is_checked_before_accepting_file(self):
        self.internal_log = "RESOURCE_EXHAUSTED: Individual quota reached"
        with self.assertRaises(QuotaExceeded):
            self.invoke()

    def test_success_exit_with_denied_action_reports_permission_error(self):
        self.answer = None
        self.stdout = json.dumps({"status": "SUCCESS", "response": "", "denied_actions": [{"action": "write_file"}]}).encode()
        with self.assertRaisesRegex(AgyPermissionError, "setup-agy"):
            self.invoke()

    def test_setup_preserves_permissions_and_grants_only_workspace(self):
        settings = Path(self.temp.name) / "settings.json"
        original = {"trustedWorkspaces": ["original"], "permissions": {"deny": ["command(*)"], "allow": ["read_file(existing)"]}}
        settings.write_text(json.dumps(original), encoding="utf-8")
        rule = configure_workspace(self.cli.config, settings)
        updated = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(updated["trustedWorkspaces"], original["trustedWorkspaces"])
        self.assertEqual(updated["permissions"]["deny"], ["command(*)"])
        self.assertEqual(updated["permissions"]["allow"], ["read_file(existing)", rule.replace("write_file(", "read_file("), rule])
        self.assertNotIn("write_file(*)", updated["permissions"]["allow"])
        configure_workspace(self.cli.config, settings)
        self.assertEqual(json.loads(settings.read_text())["permissions"]["allow"].count(rule), 1)


class TopicTests(unittest.TestCase):
    def setUp(self):
        self.config = {**CONFIG, "topic_filters": {
            "ai-cryptanalysis": [["machine learning", "neural"], ["cryptanalysis", "side channel"]],
            "ai-digital-forensics": [["machine learning", "neural"], ["forensics", "deepfake"]],
        }}

    def test_requires_ai_and_domain_even_for_cs_cr(self):
        for abstract in ("A cryptanalysis of a cipher", "A machine learning model for translation"):
            score, detail = rule_score({**PAPER, "title": "Study", "abstract": abstract, "categories": ["cs.CR"]}, self.config)
            self.assertEqual(score, 0)
        score, detail = rule_score({**PAPER, "abstract": "Neural side-channel cryptanalysis"}, self.config)
        self.assertGreater(score, 0)
        self.assertEqual(detail["topic"], "ai-cryptanalysis")
        self.assertFalse(keyword_matches("training data", "AI"))

    def test_forensics_topic_routes_post_and_frontmatter(self):
        score, detail = rule_score({**PAPER, "abstract": "Machine learning for digital forensics"}, self.config)
        self.assertEqual(detail["topic"], "ai-digital-forensics")
        path, document = assemble({**PAPER, "topic_id": detail["topic"]}, FIXTURE["groups"], {}, [], self.config)
        self.assertTrue(path.startswith("content/ai-digital-forensics/"))
        self.assertIn('"category": "ai-digital-forensics"', document)

    def test_invalid_empty_keyword_group_rejected(self):
        with self.assertRaises(ValueError):
            validate_pipeline({"topic_filters": {"ai": [[], ["forensics"]]}})


class GitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "work"
        self.root.mkdir()
        self.remote = Path(self.temp.name) / "remote.git"
        self.run_git("init", "--bare", str(self.remote))
        self.run_git("init")
        self.run_git("config", "user.name", "Fixture")
        self.run_git("config", "user.email", "fixture@example.invalid")
        self.run_git("config", "core.autocrlf", "false")
        (self.root / "initial.txt").write_text("initial", encoding="utf-8")
        self.run_git("add", "--", "initial.txt")
        self.run_git("commit", "-m", "initial")
        self.run_git("remote", "add", "origin", str(self.remote))
        self.run_git("push", "-u", "origin", "HEAD")
        self.publisher = Publisher(self.root, CONFIG, lambda message: None)
        self.path, self.document = assemble(PAPER, FIXTURE["groups"], {}, [], CONFIG)
        self.queue = empty_queue()
        item = pin(self.queue, PAPER)
        item.update(status="done", postPath=self.path)

    def run_git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, check=True).stdout

    def prepare(self):
        self.publisher.prepare(self.path, "data/paper-queue.json", self.document, self.queue)

    def test_exact_files_committed_and_push_retry_no_duplicate_commit(self):
        (self.root / "unrelated.txt").write_text("leave alone", encoding="utf-8")
        self.prepare()
        original = self.publisher.git
        def fail_push(*args, **kwargs):
            if args[0] == "push":
                raise RuntimeError("push failed")
            return original(*args, **kwargs)
        with patch.object(self.publisher, "git", side_effect=fail_push):
            with self.assertRaises(RuntimeError):
                self.publisher.resume()
        head = self.run_git("rev-parse", "HEAD")
        self.assertEqual(set(self.run_git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()), {self.path, "data/paper-queue.json"})
        self.assertTrue(self.publisher.outbox.exists())
        self.publisher.resume()
        self.assertEqual(self.run_git("rev-parse", "HEAD"), head)
        self.assertFalse(self.publisher.outbox.exists())
        self.assertIn("?? unrelated.txt", self.run_git("status", "--short"))

    def test_recover_crash_after_commit_before_journal_update(self):
        self.prepare()
        original = self.publisher.git
        def fail_push(*args, **kwargs):
            if args[0] == "push":
                raise RuntimeError("push failed")
            return original(*args, **kwargs)
        with patch.object(self.publisher, "git", side_effect=fail_push):
            with self.assertRaises(RuntimeError):
                self.publisher.resume()
        journal = json.loads(self.publisher.outbox.read_text(encoding="utf-8"))
        journal["phase"] = "prepared"
        self.publisher.outbox.write_text(json.dumps(journal), encoding="utf-8")
        before = self.run_git("rev-parse", "HEAD")
        self.publisher.resume()
        self.assertEqual(self.run_git("rev-parse", "HEAD"), before)

    def test_existing_index_is_untouched(self):
        (self.root / "other.txt").write_text("staged", encoding="utf-8")
        self.run_git("add", "--", "other.txt")
        with self.assertRaises(RuntimeError):
            self.prepare()
        self.assertEqual(self.run_git("diff", "--cached", "--name-only").strip(), "other.txt")


if __name__ == "__main__":
    unittest.main()
