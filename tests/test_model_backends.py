import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from garden import ROOT, Garden, ModelCLI, validate_config
from model_config import DEFAULT_MODEL, resolve_model
from paper_config import validate_pipeline
from paper_llm import AgyBackend, TextCLIBackend, QuotaExceeded, create_backend
from paper_pipeline import Pipeline


class RoutingTests(unittest.TestCase):
    def test_model_only_routing(self):
        for value, expected in [("", ("gemini", DEFAULT_MODEL)),
                                ("gemini/custom", ("gemini", "custom")),
                                ("codex", ("codex", "")),
                                ("gpt-example", ("codex", "gpt-example")),
                                ("codex/custom", ("codex", "custom")),
                                ("claude", ("claude", "")),
                                ("claude/sonnet", ("claude", "sonnet")),
                                ("claude-example", ("claude", "claude-example"))]:
            with self.subTest(value=value):
                self.assertEqual(resolve_model(value), expected)

    def test_invalid_models_rejected_by_both_config_paths(self):
        config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        for value in (None, [], "bad/model", "codex/", "--model", "a;echo", "claude/a/b"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_config({**config, "model": value})
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_pipeline({"model": value})

    def test_pipeline_inherits_saved_ui_model_and_allows_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
            (root / "config.json").write_text(json.dumps(raw), encoding="utf-8")
            garden = Garden(root)
            for value, backend_type in (("claude/sonnet", TextCLIBackend), ("codex", TextCLIBackend),
                                        (DEFAULT_MODEL, AgyBackend)):
                settings = {k: v for k, v in raw.items() if k != "pipeline"}
                settings["model"] = value
                garden.save_config(settings)
                pipeline = Pipeline(root)
                self.assertEqual(pipeline.config["model"], value)
                self.assertIsInstance(pipeline.backend, backend_type)
            settings = garden.config()
            settings["pipeline"]["model"] = "claude/opus"
            garden.save_config(settings)
            self.assertEqual(Pipeline(root).backend.model, "opus")

    def test_gemini_factory_strips_provider_prefix(self):
        backend = create_backend(validate_pipeline({"model": "gemini/custom"}))
        self.assertIsInstance(backend, AgyBackend)
        self.assertEqual(backend.config["model"], "custom")

    def test_web_dispatch_passes_model_and_validates_summary(self):
        body = "## Summary\n" + "Evidence. " * 20
        with patch("paper_llm.TextCLIBackend.generate", return_value=body) as generate:
            self.assertEqual(ModelCLI().summarize({"instructions": ""}, {"abstract": "evidence"}, "claude/sonnet"), body)
            self.assertIn("evidence", generate.call_args.args[0])
        with patch("garden.GeminiCLI.summarize", return_value=body) as summarize:
            ModelCLI().summarize({}, {}, "gemini/custom")
            self.assertEqual(summarize.call_args.args[-1], "custom")


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = {**validate_pipeline({}), "agy_work_dir": self.temp.name}
        self.answer = "requested answer"
        self.stdout = json.dumps({"subtype": "success", "is_error": False, "result": self.answer}).encode()
        self.stderr = b""
        self.returncode = 0

    def spawn(self, command, **kwargs):
        self.command, self.kwargs = command, kwargs
        self.prompt = kwargs["stdin"].read().decode("utf-8")
        if "--output-last-message" in command and self.answer is not None:
            Path(command[command.index("--output-last-message") + 1]).write_text(self.answer, encoding="utf-8")
        process = Mock()
        process.communicate.return_value = self.stdout, self.stderr
        process.poll.return_value = self.returncode
        process.returncode = self.returncode
        return process

    def invoke(self, model):
        with patch("paper_llm.shutil.which", return_value="cli.exe"), patch("paper_llm.subprocess.Popen", side_effect=self.spawn):
            return TextCLIBackend({**self.config, "model": model}).generate("untrusted evidence $(command)")

    def test_codex_final_file_and_claude_json(self):
        for model in ("codex/custom", "claude/sonnet"):
            with self.subTest(model=model):
                self.assertEqual(self.invoke(model), self.answer)
                self.assertFalse(self.kwargs["shell"])
                self.assertIn("$(command)", self.prompt)
                self.assertNotIn("$(command)", " ".join(self.command))
                self.assertEqual(self.command[self.command.index("--model") + 1], model.split("/")[1])
                self.assertFalse(Path(self.kwargs["cwd"]).exists())
                if model.startswith("codex"):
                    self.assertIn("read-only", self.command)
                else:
                    self.assertEqual(self.command[self.command.index("--tools") + 1], "")

    def test_codex_missing_file_never_accepts_stdout(self):
        self.answer = None
        with self.assertRaisesRegex(RuntimeError, "final answer file"):
            self.invoke("codex")

    def test_claude_invalid_and_error_envelopes(self):
        for stdout in (b"garbage", b"[]", b'{}', b'{"subtype":"success","result":42}',
                       b'{"subtype":"success","result":""}',
                       b'{"subtype":"error","is_error":true,"result":"SECRET"}'):
            self.stdout = stdout
            with self.subTest(stdout=stdout), self.assertRaises(RuntimeError) as caught:
                self.invoke("claude")
            self.assertNotIn("SECRET", str(caught.exception))

    def test_quota_and_nonzero_exit_are_sanitized(self):
        self.stdout = b'{"subtype":"error","is_error":true,"result":"RESOURCE_EXHAUSTED SECRET"}'
        with self.assertRaises(QuotaExceeded):
            self.invoke("claude")
        self.stdout = b'{"subtype":"error","is_error":true,"result":"You have hit your limit"}'
        with self.assertRaises(QuotaExceeded):
            self.invoke("claude")
        self.returncode, self.stdout, self.stderr = 1, b"", b"SECRET"
        with self.assertRaises(RuntimeError) as caught:
            self.invoke("codex")
        self.assertNotIn("SECRET", str(caught.exception))

    def test_successful_answer_can_discuss_rate_limits(self):
        self.stdout = b'{"subtype":"success","result":"HTTP 429 rate limit experiment"}'
        self.assertEqual(self.invoke("claude"), "HTTP 429 rate limit experiment")

    def test_timeout_and_streamed_quota_stop_process(self):
        for quota in (False, True):
            backend = TextCLIBackend({**self.config, "model": "codex", "timeout": 1})
            process = Mock()
            process.poll.return_value = None
            process.communicate.side_effect = subprocess.TimeoutExpired("cli", .2, stderr=b"HTTP 429" if quota else b"")
            with patch("paper_llm.shutil.which", return_value="cli.exe"), patch("paper_llm.subprocess.Popen", return_value=process), patch("paper_llm.stop_process") as stop, patch("paper_llm.time.monotonic", side_effect=[0, .1, 2]):
                with self.assertRaises(QuotaExceeded if quota else TimeoutError):
                    backend.generate("evidence")
                stop.assert_called_once_with(process)

    def test_missing_cli_has_actionable_error(self):
        with patch("paper_llm.shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "pipeline.claude_path"):
                TextCLIBackend({**self.config, "model": "claude"}).generate("evidence")
