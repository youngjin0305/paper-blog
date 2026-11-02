from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from garden import ROOT, atomic_write
from paper_research import load_atlas, seed_research, extract_candidate, enrich_graph, validate_profile
from paper_queue import empty_queue


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.atlas = load_atlas(ROOT)
        atomic_write(self.root / 'data/research-atlas.json', json.dumps(self.atlas))

    def test_seed_preserves_seen_and_existing_failed_status(self):
        q = empty_queue()
        first, second = self.atlas['papers'][:2]
        q['seen'] = [first['id']]
        q['papers'] = [{**second, 'status': 'failed', 'failCount': 3}]
        added = seed_research(self.root, q)
        self.assertNotIn(first['id'], added)
        self.assertNotIn(second['id'], added)
        self.assertEqual(q['papers'][0]['failCount'], 3)
        self.assertEqual(q['papers'][0]['status'], 'failed')
        self.assertEqual(seed_research(self.root, q), [])
        self.assertTrue(all(p['status'] == 'candidate' for p in q['papers'][1:]))

    def test_catalog_relations_have_real_endpoints_and_evidence(self):
        ids = {p['id'] for p in self.atlas['papers']}
        for r in self.atlas['relations']:
            self.assertIn(r['source'], ids)
            self.assertIn(r['target'], ids)
            self.assertTrue(r['evidence']['url'].startswith('https://'))
        for p in self.atlas['profiles'].values():
            validate_profile(p)
        self.assertGreaterEqual(len(ids), 12)

    def candidate(self):
        excerpt = 'The neural distinguisher uses ciphertext pairs from a reduced cipher.'
        value = {'contribution': '구별자 입력을 분석한다.', 'limitations': '기재 확인 안 됨',
                 'evidenceText': excerpt, 'locator': 'Section 3',
                 'studies': [{'target': 'SPECK', 'method': 'data', 'goal': '구별',
                              'conditions': '축소 라운드', 'evidenceText': excerpt}], 'relations': []}
        return value, excerpt

    def test_auto_candidate_never_becomes_reviewed_and_bad_excerpt_retries_once(self):
        value, source = self.candidate()
        bad = {**value, 'evidenceText': 'Invented source evidence not present in this paper'}
        backend = Mock(); backend.generate.side_effect = [json.dumps(bad), json.dumps(value)]
        paper = {'id': 'p', 'pdfUrl': 'https://example.org/p.pdf'}
        result = extract_candidate(paper, source, backend)
        self.assertEqual(result['status'], 'pending')
        self.assertEqual(backend.generate.call_count, 2)
        self.assertNotIn('evidenceText', result)
        graph = enrich_graph({'nodes': [{'id': 'p'}]}, {'profiles': {}, 'relations': []},
                             [{**paper, 'researchCandidate': {**result, 'status': 'reviewed'}}])
        self.assertEqual(graph['nodes'][0]['research']['status'], 'pending')

    def test_invented_parent_and_nonverbatim_evidence_rejected(self):
        value, source = self.candidate()
        value['relations'] = [{'source': 'invented', 'kind': 'extends', 'change': '확장',
                               'locator': 'Section 3', 'evidenceText': source}]
        backend = Mock(); backend.generate.return_value = json.dumps(value)
        with self.assertRaisesRegex(ValueError, 'twice'):
            extract_candidate({'id': 'p', 'pdfUrl': 'https://example.org/p.pdf'}, source, backend)
        self.assertEqual(backend.generate.call_count, 2)

    def test_missing_atlas_and_invalid_study_are_safe(self):
        self.assertEqual(load_atlas(self.root / 'empty')['papers'], [])
        p = deepcopy(next(iter(self.atlas['profiles'].values())))
        p['studies'] = 'not a list'
        with self.assertRaises(ValueError): validate_profile(p)

    def test_malformed_model_entries_retry_without_attribute_error(self):
        for field, bad in [('studies', [None]), ('relations', [None]), ('contribution', {'invalid': True})]:
            value, source = self.candidate()
            value[field] = bad
            backend = Mock(); backend.generate.return_value = json.dumps(value)
            with self.assertRaisesRegex(ValueError, 'twice'):
                extract_candidate({'id': 'p', 'pdfUrl': 'https://example.org/p.pdf'}, source, backend)
            self.assertEqual(backend.generate.call_count, 2)

    def test_semantic_relations_remain_distinct_from_citations(self):
        graph = enrich_graph({'nodes': [{'id':p['id']} for p in self.atlas['papers']], 'edges': []}, self.atlas, [])
        self.assertEqual(graph['edges'], [])
        self.assertEqual(len(graph['research']['relations']), len(self.atlas['relations']))
