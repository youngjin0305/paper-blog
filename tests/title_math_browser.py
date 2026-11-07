"""Offline regression for TeX titles on local and exported list pages."""
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app, export_site
from garden import Garden, ROOT, atomic_write
from paper_config import validate_pipeline
from paper_pipeline import assemble
from paper_queue import empty_queue, entry
from playwright.sync_api import sync_playwright, expect

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    atomic_write(root/'config.json', (ROOT/'config.json').read_text(encoding='utf-8'))
    fixture = json.loads((ROOT/'tests/fixtures/paper-pipeline.json').read_text(encoding='utf-8'))
    paper = {**fixture['papers'][0], 'topic_id': 'ai-cryptanalysis', 'title': r'NC$^1$ with $x_2$ and $$a+b$$ <safe>'}
    path, document = assemble(paper, fixture['groups'], {}, [], validate_pipeline({}), topic_ids=[paper["topic_id"]])
    atomic_write(root/path, document)
    queue = empty_queue(); queue['papers'] = [entry(paper)]; queue['seen'] = [paper['id']]
    atomic_write(root/'data/paper-queue.json',json.dumps(queue))
    garden = Garden(root); app = create_app(garden); client = app.test_client(); site = export_site(app,garden)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge',headless=True)
        page = browser.new_page(viewport={'width':1200,'height':900})
        errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
        violations=[]; page.add_init_script("document.addEventListener('securitypolicyviolation', e => console.error('CSP: '+e.violatedDirective))")
        page.on('console',lambda m:violations.append(m.text) if m.type=='error' and m.text.startswith('CSP:') else None)
        def route(request):
            from urllib.parse import urlparse
            response=client.get(urlparse(request.request.url).path)
            request.fulfill(status=response.status_code,headers=dict(response.headers),body=response.data)
        page.route('http://localhost/**',route)
        for url in ['http://localhost/','http://localhost/topics/'+paper['topic_id'],'http://localhost/reading-list',
                    (site/'index.html').as_uri(),(site/'topics'/ (paper['topic_id']+'.html')).as_uri(),(site/'reading-list.html').as_uri()]:
            page.goto(url)
            expect(page.locator('.card-title .katex')).to_have_count(3)
            expect(page.locator('.katex-error')).to_have_count(0)
            expect(page.locator('.card-title .katex-display')).to_have_count(0)
            expect(page.locator('.card-title')).to_contain_text('<safe>')
            assert page.locator('.card-title safe').count()==0
            assert page.locator('.card-title').get_attribute('href')
            # Re-running is safe and must not nest or duplicate existing equations.
            page.add_script_tag(url='http://localhost/static/math.js' if url.startswith('http:') else (site/'assets/math.js').as_uri())
            expect(page.locator('.card-title .katex')).to_have_count(3)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
        assert not errors,errors
        assert not violations,violations
        browser.close()
print('Title math passed: local/static index, topics, queue, CSP, escaping and repeat rendering')
