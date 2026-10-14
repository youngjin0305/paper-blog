"""Offline source-page, licensing, table-cell, multimodal and scoped publishing checks."""
import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from contextlib import redirect_stdout
import io
from unittest.mock import patch

import pymupdf

from app import rendered_markdown
from paper_config import validate_pipeline
from paper_visuals import (prepare_visuals, assemble_visuals, validate_visual_answer,
                           visual_document_errors, strip_visuals, table_markdown, reviewed_table)
import tests.test_paper_pipeline as pipeline_tests
import tests.test_model_backends as backend_tests


class VisualTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = validate_pipeline({})
        self.paper = {'id': 'manual:fixture', 'authors': ['Fixture Author'], 'pdfUrl': 'https://example.org/paper.pdf'}
        self.pdf = self.make_pdf()
        self.plan = {'pdfSha256': sha256(self.pdf).hexdigest(), 'license': 'CC-BY-4.0',
                     'licenseEvidence': self.paper['pdfUrl'], 'items': [
                         {'id': 'figure-1', 'page': 1, 'label': 'Figure 1', 'group': 'B',
                          'reuse': True, 'rightsReviewed': True, 'bbox': [60, 100, 400, 220]}]}
        self.save_plan()

    def make_pdf(self, licensed=True):
        with pymupdf.open() as doc:
            page = doc.new_page()
            page.insert_text((72, 70), 'Fixture Paper. ' + ('CC BY 4.0' if licensed else 'All rights reserved.'))
            page.insert_text((72, 140), 'Accuracy 82.5 percent. Training data 1000.')
            page.draw_rect((72, 155, 330, 185))
            page.insert_text((72, 210), 'Figure 1: Fixture training pipeline.')
            return doc.tobytes()

    def save_plan(self):
        path = self.root / self.config['visual_plans_path']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'version': 1, 'papers': {self.paper['id']: self.plan}}), encoding='utf-8')

    def bundle(self, dry_run=False):
        return prepare_visuals(self.root, self.paper, self.config, self.pdf, dry_run)

    def answer(self):
        return json.dumps({'items': [{'id': 'figure-1', 'readable': True,
            'explanation': '학습 데이터가 입력되는 과정과 평가 결과를 함께 보여 주는 원문 도식이다. 정확도 82.5%라는 결과를 해석할 때에는 입력 데이터의 구성 조건을 함께 살펴야 하며, 이 도식만으로 다른 암호에 대한 성능을 일반화할 수는 없다.'}]}, ensure_ascii=False)

    def test_reviewed_crop_is_bound_to_pdf_hash_page_and_license(self):
        bundle = self.bundle()
        self.assertEqual(len(bundle['assets']), 1)
        self.assertEqual(len(bundle['images']), 2)  # Source page and legible crop.
        name, data = next(iter(bundle['assets'].items()))
        self.assertEqual(Path(name).stem, sha256(data).hexdigest())
        self.assertTrue(list(self.root.rglob('page-1.png')))
        answers = validate_visual_answer(self.answer(), bundle)
        assemble_visuals(bundle, answers)
        block = bundle['blocks']['figure-1']
        self.assertIn('CC BY 4.0', block)
        self.assertIn('paper.pdf#page=1', block)
        self.assertIn('Fixture Author', block)
        self.assertEqual(visual_document_errors(block, bundle), [])
        self.assertEqual(strip_visuals('## 제시한 방법론\n내용\n\n' + block), '## 제시한 방법론\n내용')

    def test_mismatched_pdf_unknown_rights_and_outside_crop_are_rejected(self):
        original = deepcopy(self.plan)
        for changes in ({'pdfSha256': '0' * 64}, {'license': 'unknown'}, {'licenseEvidence': 'https://other.org'}):
            self.plan = {**deepcopy(original), **changes}
            self.save_plan()
            with self.assertRaises(ValueError):
                self.bundle()
        for field, value in (('bbox', [-1, 10, 500, 100]), ('rightsReviewed', False), ('page', 999), ('label', 'Figure 99')):
            self.plan = deepcopy(original)
            self.plan['items'][0][field] = value
            self.save_plan()
            with self.assertRaises(ValueError):
                self.bundle()
        self.pdf = self.make_pdf(licensed=False)
        self.plan = deepcopy(original)
        self.plan['pdfSha256'] = sha256(self.pdf).hexdigest()
        self.save_plan()
        with self.assertRaises(ValueError):
            self.bundle()

    def test_unreviewed_pages_are_private_and_have_no_republished_crop(self):
        (self.root / self.config['visual_plans_path']).unlink()
        bundle = self.bundle()
        self.assertEqual(bundle['assets'], {})
        self.assertEqual(len(bundle['images']), 1)
        self.assertEqual(bundle['items'][0]['page'], 1)

    def test_dry_run_writes_no_files(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertTrue(self.bundle(dry_run=True)['assets'])
        after = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_visual_json_rejects_invented_numbers_and_unreadable_images(self):
        bundle = self.bundle()
        for response in (self.answer().replace('82.5', '99.99'), self.answer().replace('true', 'false'),
                         self.answer().replace('figure-1', 'figure-999'), '{"items":[]}', '[]'):
            with self.assertRaises(ValueError):
                validate_visual_answer(response, bundle)
        data = json.loads(self.answer())
        data['items'].append(deepcopy(data['items'][0]))
        with self.assertRaises(ValueError):
            validate_visual_answer(json.dumps(data), bundle)

    def test_tampered_visual_blocks_cannot_hide_executable_content(self):
        bundle = self.bundle()
        assemble_visuals(bundle, validate_visual_answer(self.answer(), bundle))
        block = bundle['blocks']['figure-1']
        self.assertTrue(visual_document_errors(block + '\n\n![x](https://evil.example/x.png)', bundle))
        self.assertTrue(visual_document_errors(block.replace('82.5', '99.99'), bundle))
        self.assertTrue(visual_document_errors(block + '\n\n' + block, bundle))
        self.assertTrue(visual_document_errors(block, None))

    def test_renderer_only_allows_local_content_addressed_pngs(self):
        asset = next(iter(self.bundle()['assets']))
        html = str(rendered_markdown('![good](../' + asset + ')\n\n![bad](https://evil.example/x.png)'))
        self.assertIn('src="../' + asset + '"', html)
        self.assertNotIn('src="https://', html)
        self.assertNotIn('onerror', str(rendered_markdown('<img src=x onerror="alert(1)">')))

    def test_table_cells_remain_in_their_reviewed_rows_columns_and_units(self):
        with pymupdf.open() as doc:
            page = doc.new_page()
            for y, row in ((100, ['Model', 'Accuracy (%)']), (120, ['A', '82.5']), (140, ['B', '83.2'])):
                page.insert_text((72, y), row[0])
                page.insert_text((240, y), row[1])
            spec = {'bbox': [60, 80, 400, 150], 'columns': [60, 220, 400], 'headers': ['Model', 'Accuracy (%)']}
            rows = reviewed_table(page, spec, pymupdf.Rect(50, 50, 420, 170))
            self.assertEqual(rows, [['Model', 'Accuracy (%)'], ['A', '82.5'], ['B', '83.2']])
            self.assertIn('| A | 82.5 |', table_markdown(rows))
            self.assertIsNone(reviewed_table(page, {**spec, 'headers': ['Wrong', 'Accuracy (%)']}, pymupdf.Rect(50, 50, 420, 170)))
        self.assertIn(r'\|', table_markdown([['A|B'], ['<img src=x>']]))

    def pipeline(self, invalid=False):
        from garden import ROOT
        from paper_pipeline import Pipeline, FixtureBackend
        from paper_queue import pin
        fixture = deepcopy(pipeline_tests.FIXTURE)
        raw = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
        raw['topics'][0]['id'] = 'ai'
        raw['pipeline'] = deepcopy(pipeline_tests.CONFIG)
        (self.root / 'config.json').write_text(json.dumps(raw), encoding='utf-8')
        owner = self
        class Backend(FixtureBackend):
            supports_images = True
            def __init__(self):
                super().__init__(fixture)
                self.visual_calls = 0
            def generate(self, prompt, options=None):
                if options['kind'] == 'visuals':
                    self.visual_calls += 1
                    owner.assertTrue(options['images'])
                    return owner.answer().replace('82.5', '99.99') if invalid else owner.answer()
                return super().generate(prompt, options)
        backend = Backend()
        source = SimpleNamespace(last_pdf=self.pdf, fulltext=lambda p: (fixture['markdown'], fixture['source_text']))
        pipeline = Pipeline(self.root, backend=backend, source=source)
        paper = {**pipeline_tests.PAPER, 'id': self.paper['id'], 'source': 'manual',
                 'url': 'https://example.org/paper', 'pdfUrl': self.paper['pdfUrl'], 'topic_id': 'ai'}
        pin(pipeline.queue, paper)
        return pipeline, backend

    def test_daily_publishes_only_validated_visuals_and_assets(self):
        pipeline, backend = self.pipeline()
        with redirect_stdout(io.StringIO()), patch.object(pipeline.publisher, 'preflight'), \
                patch.object(pipeline.publisher, 'prepare') as publish, patch.object(pipeline.publisher, 'resume'):
            result = pipeline.daily()
        self.assertTrue(result['valid'], result['errors'])
        self.assertEqual(backend.visual_calls, 1)
        self.assertIn('### 원문 시각자료', result['document'])
        self.assertEqual(len(publish.call_args.kwargs['assets']), 1)

    def test_failed_visual_validation_retries_once_and_never_publishes(self):
        pipeline, backend = self.pipeline(invalid=True)
        with redirect_stdout(io.StringIO()), patch.object(pipeline.publisher, 'preflight'), \
                patch.object(pipeline.publisher, 'prepare') as publish:
            result = pipeline.daily()
        self.assertFalse(result['valid'])
        self.assertEqual(backend.visual_calls, 2)
        publish.assert_not_called()
        self.assertTrue(any('99.99' in error for error in result['errors']))
        self.assertEqual(pipeline.queue['papers'][0]['status'], 'failed')


class VisualAdapterTests(unittest.TestCase):
    setUp = backend_tests.AdapterTests.setUp
    spawn = backend_tests.AdapterTests.spawn
    def test_claude_images_are_structured_stdin_without_tools(self):
        png = b'\x89PNG\r\n\x1a\nfixture'
        from paper_llm import TextCLIBackend
        backend = TextCLIBackend({**self.config, 'model': 'claude/opus'})
        with patch('paper_llm.shutil.which', return_value='claude.exe'), patch('paper_llm.subprocess.Popen', side_effect=self.spawn):
            backend.generate('image evidence', {'images': [png]})
        envelope = json.loads(self.prompt)
        image = envelope['message']['content'][0]
        self.assertEqual(base64.b64decode(image['source']['data']), png)
        self.assertIn('--input-format', self.command)
        self.assertEqual(self.command[self.command.index('--tools') + 1], '')
        self.assertNotIn('image evidence', ' '.join(self.command))
        with self.assertRaises(ValueError):
            TextCLIBackend({**self.config, 'model': 'codex'}).generate('evidence', {'images': [png]})


class VisualGitTests(unittest.TestCase):
    setUp = pipeline_tests.GitTests.setUp
    run_git = pipeline_tests.GitTests.run_git
    def asset(self):
        data = b'\x89PNG\r\n\x1a\nfixture'
        return f'static/paper-figures/{"a" * 20}/{sha256(data).hexdigest()}.png', data

    def test_assets_are_committed_with_post_and_recover_without_duplicate_commit(self):
        name, data = self.asset()
        (self.root / 'unrelated.txt').write_text('do not stage')
        self.publisher.prepare(self.path, 'data/paper-queue.json', self.document, self.queue, assets={name: data})
        original = self.publisher.git
        def fail_push(*args, **kwargs):
            if args[0] == 'push':
                raise RuntimeError('push failed')
            return original(*args, **kwargs)
        with patch.object(self.publisher, 'git', side_effect=fail_push), self.assertRaises(RuntimeError):
            self.publisher.resume()
        journal = json.loads(self.publisher.outbox.read_text(encoding='utf-8'))
        journal['phase'] = 'prepared'  # Crash immediately after commit.
        self.publisher.outbox.write_text(json.dumps(journal), encoding='utf-8')
        head = self.run_git('rev-parse', 'HEAD')
        self.publisher.resume()
        self.assertEqual(self.run_git('rev-parse', 'HEAD'), head)
        self.assertEqual((self.root / name).read_bytes(), data)
        self.assertEqual(set(self.run_git('diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD').splitlines()),
                         {name, self.path, 'data/paper-queue.json'})
        self.assertIn('?? unrelated.txt', self.run_git('status', '--short'))

    def test_changed_asset_or_outside_asset_path_is_rejected(self):
        name, data = self.asset()
        with self.assertRaises(ValueError):
            self.publisher.prepare(self.path, 'data/paper-queue.json', self.document, self.queue, assets={'../outside.png': data})
        self.publisher.prepare(self.path, 'data/paper-queue.json', self.document, self.queue, assets={name: data})
        target = self.root / name
        target.parent.mkdir(parents=True)
        target.write_bytes(b'edited by another task')
        with self.assertRaises(RuntimeError):
            self.publisher.resume()
