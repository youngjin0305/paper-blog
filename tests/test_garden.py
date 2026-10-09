import json
from pathlib import Path
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from subprocess import CompletedProcess

from app import create_app, export_site, rendered_markdown
from garden import Arxiv, Garden, GeminiCLI, ROOT, validate_config, summary_sort_time, summary_display


PAPER = {"id": "2609.00001v1", "title": "A fixture paper", "abstract": "Test abstract, not a real research result.",
         "published": "2026-09-01T00:00:00Z", "updated": "2026-09-01T00:00:00Z", "authors": ["Test Author"],
         "url": "https://arxiv.org/abs/2609.00001v1", "pdf": "https://arxiv.org/pdf/2609.00001v1"}


class FakeSource:
    def search(self, topic):
        return [PAPER], 1


class FakeSummary:
    calls = 0
    def summarize(self, topic, paper, model):
        self.calls += 1
        return "## 한눈에 보기\n\n테스트 요약입니다.\n\n## 초록\n\n실제 연구 결과가 아닌 테스트용 초록입니다.\n\n## 한계와 확인할 점\n\n초록에서 확인 불가."


class GardenTests(unittest.TestCase):
    def test_summary_metadata_fields_are_independent(self):
        stamp = "2026-09-24T14:15:03+09:00"
        display = summary_display({"summarized_at": stamp})
        self.assertEqual(display["summary_date"], "2026-09-24")
        self.assertNotIn("summary_model", display)
        for bad in (None, "", "invalid", 123, "2026-09-24"):
            display = summary_display({"summary_model": "claude-opus-5", "summarized_at": bad})
            self.assertEqual(display["summary_model_label"], "Claude Opus 5")
            self.assertNotIn("summary_date", display)
        self.assertEqual(summary_display({"summary_model": 123, "summarized_at": stamp})["summary_date"], "2026-09-24")
        self.assertEqual(summary_display({"review_method": "codex-manual"})["summary_model_caption"],
                         "Codex 직접 정리 · 모델 ID 미확인")
        reported = summary_display({"summary_model": "claude-opus-5", "summary_model_source": "reported"})
        self.assertEqual(reported["summary_model_caption"], "정리 모델: Claude Opus 5")
        self.assertIn("CLI 응답", reported["summary_model_provenance"])
        configured = summary_display({"summary_model": "claude/opus", "summary_model_source": "configured"})
        self.assertEqual(configured["summary_model_caption"], "정리 모델: Claude Opus (버전 미기록) (요청값)")
        self.assertEqual(summary_display({"summarized_at": "2026-09-24T23:30:00Z"})["summary_date"], "2026-09-25")

    def test_date_only_post_in_live_static_and_sorting(self):
        from paper_validation import split_document
        self.garden.research()
        post = self.garden.posts()[0]
        path = self.root / post["path"]
        metadata, body = split_document(path.read_text(encoding="utf-8"))
        metadata.pop("summary_model")
        metadata["summarized_at"] = "2026-09-24T14:15:03+09:00"
        for basis in ("abstract", "fulltext"):
            with self.subTest(basis=basis):
                metadata["basis"] = basis
                path.write_text("---\n" + json.dumps(metadata) + "\n---\n" + body, encoding="utf-8")
                actual = self.garden.post(post["id"])
                self.assertEqual(actual["summary_date"], "2026-09-24")
                self.assertEqual(summary_sort_time(actual), datetime(2026, 9, 24, 5, 15, 3, tzinfo=timezone.utc))
                site = export_site(self.app, self.garden)
                for html in (self.client.get("/").get_data(as_text=True),
                             self.client.get('/posts/' + post["id"]).get_data(as_text=True),
                             (site / "index.html").read_text(encoding="utf-8"),
                             (site / "posts" / (post["id"] + ".html")).read_text(encoding="utf-8")):
                    self.assertIn("2026-09-24", html)
                    self.assertNotIn("날짜 미기록", html)

    def test_summary_sort_normalizes_timezones_and_legacy_dates(self):
        older = {"summarized_at": "2026-09-28T09:00:00+09:00", "published": "2026-09-28"}
        newer = {"summarized_at": "2026-09-28T01:00:00Z", "published": "2020-01-01"}
        self.assertGreater(summary_sort_time(newer), summary_sort_time(older))
        self.assertEqual(summary_sort_time({"created": newer["summarized_at"]}), summary_sort_time(newer))
        self.assertEqual(summary_sort_time({"summarized_at": "invalid", "created": newer["summarized_at"]}), summary_sort_time(newer))

    def test_live_and_export_lists_sort_by_summary_date(self):
        topic = self.garden.config()["topics"][0]
        body = FakeSummary().summarize(None, None, None)
        with patch("garden.now", return_value="2026-09-28T02:00:00Z"):
            self.garden.store_post(topic, {**PAPER, "id": "old-paper", "title": "Older paper summarized later", "published": "2020-01-01T00:00:00Z"}, body)
        with patch("garden.now", return_value="2026-09-28T01:00:00Z"):
            self.garden.store_post(topic, {**PAPER, "id": "new-paper", "title": "Newer paper summarized earlier"}, body)
        self.assertEqual(self.garden.posts()[0]["title"], "Older paper summarized later")
        site = export_site(self.app, self.garden)
        for html in (self.client.get("/").get_data(as_text=True), self.client.get("/topics/ai").get_data(as_text=True),
                     (site / "index.html").read_text(encoding="utf-8"), (site / "topics/ai.html").read_text(encoding="utf-8")):
            self.assertLess(html.index("Older paper summarized later"), html.index("Newer paper summarized earlier"))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        config["schedule_enabled"] = False
        config["topics"] = config["topics"][:1]
        config["topics"][0]["id"] = "ai"
        config["pipeline"].update(category="ai", post_dir="content/ai", topic_filters={}, topic_exclusions={})
        (self.root / "config.json").write_text(json.dumps(config), encoding="utf-8")
        self.summary = FakeSummary()
        self.garden = Garden(self.root, FakeSource(), self.summary)
        self.app = create_app(self.garden)
        self.app.testing = True
        self.client = self.app.test_client()
        page = self.client.get("/").get_data(as_text=True)
        self.token = re.search('name="garden-token" content="([^"]+)"', page).group(1)

    def tearDown(self):
        self.temp.cleanup()

    def test_duplicate_is_not_summarized_twice(self):
        self.assertEqual(self.garden.research(), ["success"])
        self.garden.research()
        self.assertEqual(len(self.garden.posts()), 1)
        self.assertEqual(self.summary.calls, 1)
        md = self.garden.markdown(self.garden.posts()[0])
        self.assertIn('"basis": "abstract"', md)
        self.assertIn(PAPER["url"], md)
        self.assertIn("## 초록", md)
        self.assertNotIn(PAPER["abstract"], md)
        self.assertIn("실제 연구 결과가 아닌 테스트용 초록", md)

    def test_classification_only_topic_has_no_search(self):
        config = self.garden.config()
        config["topics"].append({"id": "pqc-migration", "name": "PQC Migration", "description": "",
            "query": "", "instructions": "", "interval_hours": 24, "lookback_days": 7,
            "max_papers": 5, "enabled": False})
        self.garden.save_config(config)
        self.assertNotIn("pqc-migration", self.garden.due_topics())
        with self.assertRaisesRegex(ValueError, "분류 전용"):
            self.garden.research("pqc-migration")
        response = self.client.post('/api/research', json={"topic_id": "pqc-migration"},
                                    headers={"X-Garden-Token": self.token})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('data-research="pqc-migration"', self.client.get('/topics/pqc-migration').get_data(as_text=True))

    def test_cards_use_topic_summary_in_live_and_exported_pages(self):
        self.garden.research()
        self.assertEqual(self.garden.posts()[0]["summary"], "테스트 요약입니다.")
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('테스트 요약입니다.</p>', html)
        site = export_site(self.app, self.garden)
        self.assertIn('테스트 요약입니다.</p>', (site / "index.html").read_text(encoding="utf-8"))

    def test_new_posts_record_model_and_korean_summary_date(self):
        self.garden.research()
        post = self.garden.posts()[0]
        self.assertEqual(post["authors"], PAPER["authors"])
        self.assertEqual(post["summary_model"], self.garden.config()["model"])
        self.assertTrue(post["summarized_at"].endswith("+09:00"))
        self.assertEqual(post["summary_date"], post["summarized_at"][:10])
        html = self.client.get(f'/posts/{post["id"]}').get_data(as_text=True)
        self.assertIn("정리 모델: " + post["summary_model_label"], html)
        self.assertIn("정리 날짜: " + post["summary_date"], html)
        self.assertIn("저자</strong><span>Test Author", html)
        site = export_site(self.app, self.garden)
        self.assertIn("정리 모델: " + post["summary_model_label"], (site / f'posts/{post["id"]}.html').read_text(encoding="utf-8"))

    def test_legacy_and_demo_posts_do_not_invent_model_provenance(self):
        self.garden.store_post(self.garden.config()["topics"][0], PAPER, FakeSummary().summarize(None, None, None))
        post = self.garden.posts()[0]
        self.assertNotIn("summary_model", post)
        self.assertNotIn("정리 모델:", self.client.get(f'/posts/{post["id"]}').get_data(as_text=True))
        self.garden.seed_demo()
        self.assertTrue(all("summary_model" not in p for p in self.garden.posts()))

    def test_failure_remains_retryable(self):
        with patch.object(self.summary, "summarize", side_effect=RuntimeError("quota")):
            self.assertEqual(self.garden.research(), ["failed"])
        self.assertEqual(len(self.garden.posts()), 0)
        self.assertEqual(self.garden.research(), ["success"])
        self.assertEqual(len(self.garden.posts()), 1)

    def test_partial_run_retains_completed_papers(self):
        second = {**PAPER, "id": "2609.00002v1"}
        with patch.object(self.garden.source, "search", return_value=([PAPER, second], 2)), patch.object(self.summary, "summarize", side_effect=["## Summary\nFirst completed.", RuntimeError("quota")]):
            self.assertEqual(self.garden.research(), ["partial"])
        self.assertEqual(len(self.garden.posts()), 1)
        self.assertEqual(self.garden.status()["runs"][0]["added"], 1)

    def test_schedule_respects_off_and_persists_interval(self):
        self.assertEqual(self.garden.research(due_only=True), [])
        config = self.garden.config(); config["schedule_enabled"] = True
        self.garden.save_config(config)
        self.assertEqual(self.garden.due_topics(), ["ai"])
        self.garden.research(due_only=True)
        self.assertEqual(self.garden.due_topics(), [])
        restarted = Garden(self.root, FakeSource(), self.summary)
        self.assertEqual(restarted.due_topics(), [])
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        with self.garden.db() as db:
            db.execute("UPDATE schedule SET last_attempt=?", (old,))
        self.assertEqual(restarted.due_topics(), ["ai"])

    def test_local_write_protection_and_validation(self):
        config = self.garden.config()
        self.assertEqual(self.client.post("/api/config", json=config).status_code, 403)
        headers = {"X-Garden-Token": self.token}
        config["topics"][0]["id"] = "../escape"
        self.assertEqual(self.client.post("/api/config", json=config, headers=headers).status_code, 400)
        self.assertEqual(self.garden.config()["topics"][0]["id"], "ai")
        self.assertEqual(self.client.get("/", headers={"Host": "attacker.example"}).status_code, 400)
        self.assertEqual(self.client.post("/api/research", json=[], headers=headers).status_code, 400)

    def test_no_model_output_scripts(self):
        rendered = str(rendered_markdown('<script>alert(1)</script>\n\n[bad](javascript:alert(1))\n\n<img src=x onerror=alert(1)>'))
        self.assertNotIn("<script", rendered)
        self.assertNotIn("javascript:", rendered)
        self.assertNotIn("onerror", rendered)
        self.garden.research()
        identifier = self.garden.posts()[0]["id"]
        self.assertIn("style-src-attr 'unsafe-inline'", self.client.get(f"/posts/{identifier}").headers["Content-Security-Policy"])
        self.assertNotIn("style-src-attr 'unsafe-inline'", self.client.get("/").headers["Content-Security-Policy"])

    def test_pages_download_search_and_export(self):
        self.garden.research()
        identifier = self.garden.posts()[0]["id"]
        for path in ("/", "/topics/ai", "/settings", f"/posts/{identifier}", f"/posts/{identifier}/markdown", "/api/status"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertNotIn("A fixture paper", self.client.get("/?q=notfound").get_data(as_text=True))
        self.assertIn("A fixture paper", self.client.get("/?q=테스트%20요약").get_data(as_text=True))
        self.assertIn("A fixture paper", self.client.get("/?q=Test%20Author").get_data(as_text=True))
        self.assertEqual(self.garden.posts(query="존재하지 않는 단어"), [])
        site = export_site(self.app, self.garden)
        self.assertTrue((site / "index.html").exists())
        self.assertTrue((site / "topics/ai.html").exists())
        search_data = (site / "assets/search-data.js").read_text(encoding="utf-8")
        self.assertIn(identifier, search_data)
        self.assertIn("search-data.js", (site / "index.html").read_text(encoding="utf-8"))
        self.assertIn("search.js", (site / "topics/ai.html").read_text(encoding="utf-8"))
        self.assertIn('data-post-id="' + identifier + '"', (site / "index.html").read_text(encoding="utf-8"))
        self.assertIn("논문 검색", (site / "index.html").read_text(encoding="utf-8"))
        post = (site / f"posts/{identifier}.html").read_text(encoding="utf-8")
        self.assertIn('../assets/style.css', post)
        self.assertNotIn('app.js', post)
        self.assertNotIn(self.token, post)
        for html_path in site.rglob("*.html"):
            html = html_path.read_text(encoding="utf-8")
            for href in re.findall('href="([^"]+)"', html):
                if not href.startswith(("https:", "http:", "#")):
                    self.assertTrue((html_path.parent / href).exists(), f"Broken export link {href}")

    def test_demo_is_explicit_and_idempotent(self):
        self.garden.seed_demo(); self.garden.seed_demo()
        self.assertEqual(len(self.garden.posts()), 1)
        post = self.garden.posts()[0]
        self.assertEqual(post["demo"], 1)
        self.assertIn("최신 조사 결과가 아닙니다", self.garden.markdown(post))

    def test_invalid_boolean_and_limits(self):
        for key, value in (("max_papers", 10000), ("interval_hours", True), ("enabled", "true")):
            config = self.garden.config(); config["topics"][0][key] = value
            with self.assertRaises(ValueError):
                validate_config(config)

    def test_atom_parser_filters_by_date_and_rejects_errors(self):
        xml = b'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:o="http://a9.com/-/spec/opensearch/1.1/"><o:totalResults>1</o:totalResults><entry><id>http://arxiv.org/abs/2609.00001v1</id><title>A\n paper</title><summary>Abstract</summary><published>2026-09-01T00:00:00Z</published><updated>2026-09-01T00:00:00Z</updated><author><name>Author</name></author></entry></feed>'''
        papers, total = Arxiv.parse(xml, datetime(2026, 8, 31, tzinfo=timezone.utc))
        self.assertEqual(total, 1); self.assertEqual(papers[0]["title"], "A paper")
        self.assertEqual(papers[0]["url"], PAPER["url"])
        self.assertEqual(Arxiv.parse(xml, datetime(2026, 9, 2, tzinfo=timezone.utc))[0], [])
        with self.assertRaises(ValueError):
            Arxiv.parse(b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/api/errors#bad</id><summary>Bad query</summary></entry></feed>', datetime.now(timezone.utc))

    def test_gemini_uses_stdin_no_shell_and_google_auth(self):
        cli = GeminiCLI(self.root)
        body = "## 한눈에 보기\n" + "초록 기반 요약입니다. " * 20
        with patch.object(cli, "command", return_value=["node", "cli.js"]), patch("garden.subprocess.run", return_value=CompletedProcess([], 0, json.dumps({"response": body}), "")) as run:
            self.assertEqual(cli.summarize(self.garden.config()["topics"][0], PAPER), body.strip())
            kwargs = run.call_args.kwargs
            self.assertFalse(kwargs["shell"])
            self.assertIn(PAPER["abstract"], kwargs["input"])
            self.assertNotIn("GEMINI_API_KEY", kwargs["env"])
            self.assertIn("GEMINI_CLI_SYSTEM_SETTINGS_PATH", kwargs["env"])
        with patch.object(cli, "command", return_value=["node", "cli.js"]), patch("garden.subprocess.run", return_value=CompletedProcess([], 1, "", "SECRET")):
            with self.assertRaises(RuntimeError) as result:
                cli.summarize(self.garden.config()["topics"][0], PAPER)
            self.assertNotIn("SECRET", str(result.exception))

    def test_crash_marks_orphan_run_interrupted(self):
        with self.garden.db() as db:
            db.execute("INSERT INTO runs(id,topic_id,started,status) VALUES('old','ai','2026-01-01','running')")
        restarted = Garden(self.root, FakeSource(), self.summary)
        self.assertEqual(restarted.status()["runs"][0]["status"], "interrupted")


if __name__ == "__main__":
    unittest.main()
