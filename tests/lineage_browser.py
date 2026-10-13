"""Offline checks for a continuous field timeline, year rows and full relations."""
import json
from pathlib import Path
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app, export_site, graph_script
from garden import Garden, ROOT, atomic_write
from playwright.sync_api import expect, sync_playwright
from waitress import create_server


def node(identifier, year, precision="day", **changes):
    return {"id": identifier, "title": "Fixture paper " + identifier, "authors": ["Fixture Author"],
            "year": year, "date": f"{year}-01-01T00:00:00Z", "timeOrder": year * 1000,
            "datePrecision": precision, "topic": "ai-cryptanalysis", "topicLabel": "AI CryptAnalysis",
            "group": "Cryptography", "core": True, "summaryId": None, "url": "https://example.org/" + identifier,
            "venue": "Fixture venue", "venueConfirmed": True, "recommended": True, "inScope": True,
            "score": 4, "conceptLabels": ["Fixture concept"], "qualityReason": "Fixture policy",
            "status": "Fixture pending", **changes}


def citation(source, target):
    return {"source": source, "target": target, "kind": "citation", "evidence": {
        "match": "DOI", "origin": "original-references", "checkedAt": "2026-10-13T00:00:00Z",
        "excerpt": "Verbatim fixture reference.", "url": "https://example.org/evidence"}}


def assert_clear_connectors(page):
    crossings = page.locator('.lineage-edge').evaluate_all("""paths => paths.flatMap(path => {
      const svgBox = path.ownerSVGElement.getBoundingClientRect();
      const cards = [...path.closest('.lineage-canvas').querySelectorAll('.lineage-card')]
        .filter(card => ![path.dataset.source, path.dataset.target].includes(card.dataset.nodeId));
      for (let offset = 5; offset < path.getTotalLength() - 5; offset += 5) {
        const point = path.getPointAtLength(offset);
        const x = svgBox.left + point.x, y = svgBox.top + point.y;
        for (const card of cards) {
          const box = card.getBoundingClientRect();
          if (x > box.left + 2 && x < box.right - 2 && y > box.top + 2 && y < box.bottom - 2)
            return [path.dataset.source + ' -> ' + path.dataset.target + ' crosses ' + card.dataset.nodeId];
        }
      }
      return [];
    })""")
    assert not crossings, crossings


data = {"nodes": [node("a", 2010), node("b", 2015), node("c", 2017),
                  node("d", 2020, summaryId="fixture-summary"), node("e", 2021, "year"),
                  node("f", 2021, "year"), node("g", 2022, title="Related <img src=x onerror=alert(1)>"),
                  node("h", 2019, core=False, recommended=False, inScope=False)],
        "edges": [citation("a", "b"), citation("a", "c"), citation("b", "d"), citation("c", "d"),
                  citation("d", "e"), citation("e", "f"), citation("a", "h"),
                  {"source": "f", "target": "g", "kind": "related", "similarity": .4, "reason": "Fixture inference"}],
        "settings": {"max_nodes": 60}}

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    config["schedule_enabled"] = False
    atomic_write(root / "config.json", json.dumps(config))
    garden = Garden(root)
    app = create_app(garden)
    site = export_site(app, garden)
    atomic_write(site / "assets/research-graph-data.js", graph_script(data))
    atomic_write(site / "posts/fixture-summary.html", "<h1>Fixture summary destination</h1>")
    server = create_server(app, host="127.0.0.1", port=0)
    threading.Thread(target=server.run, daemon=True).start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors, csp = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: csp.append(message.text) if "Content Security Policy" in message.text else None)
            url = site.joinpath("research-lineage.html").as_uri()
            page.goto(url)
            expect(page.locator('.lineage-card')).to_have_count(7)
            expect(page.locator('.lineage-field')).to_have_count(1)
            expect(page.locator('.lineage-edge')).to_have_count(7)
            expect(page.locator('.lineage-year-label')).to_have_count(6)
            expect(page.locator('.lineage-year-row[data-year="2021"] .lineage-card')).to_have_count(2)
            expect(page.locator('.lineage-card .lineage-year')).to_have_count(0)
            assert page.locator('.sidebar a[href*="research-lineage"]').count() == 0
            assert page.locator('img').count() == 0, "Titles must be literal text"
            assert page.locator('.lineage-edge[data-source="c"][data-target="d"]').count() == 1
            assert page.locator('.lineage-edge[data-source="b"][data-target="d"]').count() == 1
            assert page.locator('.lineage-edge[data-source="e"][data-target="f"]').count() == 1
            cards = page.locator('.lineage-card').evaluate_all("els => Object.fromEntries(els.map(e => [e.dataset.nodeId, {top:e.getBoundingClientRect().top,bottom:e.getBoundingClientRect().bottom}]))")
            for source, target in (("a", "b"), ("a", "c"), ("c", "d"), ("d", "e")):
                assert cards[source]["bottom"] < cards[target]["top"], "Every branch must point down"
            assert_clear_connectors(page)
            page.locator('.lineage-edge-hit').first.scroll_into_view_if_needed()
            point = page.locator('.lineage-edge-hit').first.evaluate("""path => {
              const point = path.getPointAtLength(path.getTotalLength() / 2);
              const box = path.ownerSVGElement.getBoundingClientRect();
              return {x:box.left + point.x, y:box.top + point.y};
            }""")
            page.mouse.click(point['x'], point['y'])
            expect(page.locator('#lineage-dialog')).to_be_visible()
            expect(page.locator('#lineage-details blockquote')).to_have_text('Verbatim fixture reference.')
            page.keyboard.press('Escape')
            page.locator('[data-node-id="d"] .lineage-info').click()
            expect(page.locator('#lineage-dialog')).to_be_visible()
            expect(page.locator('#lineage-details li')).to_have_count(3)
            page.locator('#lineage-details li button').first.click()
            expect(page.locator('#lineage-details blockquote')).to_have_text('Verbatim fixture reference.')
            page.keyboard.press('Escape')
            page.locator('#flow-links').select_option('citation')
            expect(page.locator('.lineage-edge')).to_have_count(6)
            page.locator('#flow-links').select_option('all')
            expect(page.locator('.lineage-edge.related')).to_have_count(1)
            page.locator('.lineage-edge-hit[aria-label^="주제 연결"]').focus()
            page.keyboard.press('Enter')
            expect(page.locator('#lineage-detail-title')).to_have_text('주제 연결 · 추정')
            page.keyboard.press('Escape')
            page.locator('#flow-quality').select_option('all')
            expect(page.locator('.lineage-card')).to_have_count(8)
            page.locator('#flow-reviewed').check()
            expect(page.locator('.lineage-card')).to_have_count(1)
            page.locator('.lineage-title').click()
            expect(page.locator('h1')).to_have_text('Fixture summary destination')
            page.goto(url)
            page.locator('#flow-search').fill('not-in-fixture')
            expect(page.locator('#lineage-empty')).to_be_visible()
            page.locator('#flow-search').fill('paper d')
            expect(page.locator('.lineage-card.focused')).to_have_count(1)
            expect(page.locator('.lineage-card')).to_have_count(4)
            page.locator('#flow-search').fill('')
            expect(page.locator('.lineage-card')).to_have_count(7)
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator('[data-node-id="a"]').scroll_into_view_if_needed()
            page.wait_for_function("document.querySelector('.lineage-cells').dataset.columns === '1'")
            assert_clear_connectors(page)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), "Mobile must not overflow"
            before = page.evaluate('scrollY')
            page.mouse.move(190, 550); page.mouse.wheel(0, 600)
            page.wait_for_function('(before) => scrollY > before', arg=before)
            # A complete citation chain draws only consecutive steps. Keep
            # independent branches in the original fixture above intact.
            chain_nodes = [node('chain-' + str(i), 2010 + i) for i in range(4)]
            chain_nodes[0]['summaryId'] = 'fixture-root'
            chain_nodes[3]['summaryId'] = 'fixture-summary'
            chain = {'nodes': chain_nodes, 'edges': [citation(chain_nodes[i]['id'], chain_nodes[j]['id'])
                     for i in range(4) for j in range(i + 1, 4)], 'settings': {'max_nodes': 60}}
            page.set_viewport_size({'width': 1440, 'height': 1000})
            atomic_write(site / 'assets/research-graph-data.js', graph_script(chain))
            page.goto(url + '?case=chain', wait_until='networkidle')
            expect(page.locator('.lineage-edge')).to_have_count(3)
            expect(page.locator('#lineage-count')).to_contain_text('중복 연결 3개 생략')
            assert page.locator('.lineage-edge[data-source="chain-0"][data-target="chain-3"]').count() == 0
            page.locator('[data-node-id="chain-3"] .lineage-info').click()
            expect(page.locator('#lineage-details li')).to_have_count(3)
            page.keyboard.press('Escape')
            page.locator('#lineage-show-all').check()
            expect(page.locator('.lineage-edge')).to_have_count(6)
            page.locator('#lineage-show-all').uncheck()
            page.locator('#flow-reviewed').check()
            expect(page.locator('.lineage-card')).to_have_count(2)
            expect(page.locator('.lineage-edge')).to_have_count(1)
            assert page.locator('.lineage-edge[data-source="chain-0"][data-target="chain-3"]').count() == 1
            # An explicit exception preserves an existing direct citation only.
            chain['settings']['lineage_keep_edges'] = [{'source': 'chain-0', 'target': 'chain-3', 'reason': 'Fixture important direct comparison'}]
            atomic_write(site / 'assets/research-graph-data.js', graph_script(chain))
            page.goto(url + '?case=exception', wait_until='networkidle')
            expect(page.locator('.lineage-edge')).to_have_count(4)
            expect(page.locator('.lineage-edge.preserved')).to_have_count(1)
            expect(page.locator('#lineage-exception-legend')).to_be_visible()
            page.locator('[data-node-id="chain-3"] .lineage-info').click()
            page.locator('#lineage-details li button').first.click()
            expect(page.locator('.lineage-keep-reason')).to_contain_text('Fixture important direct comparison')
            page.keyboard.press('Escape')
            # An inferred alternate path cannot hide a verified direct citation.
            mixed = {'nodes': chain_nodes[:3], 'edges': [citation('chain-0', 'chain-2'),
                     {'source': 'chain-0', 'target': 'chain-1', 'kind': 'related', 'similarity': .4, 'reason': 'Fixture inference'},
                     citation('chain-1', 'chain-2')], 'settings': {'max_nodes': 60}}
            atomic_write(site / 'assets/research-graph-data.js', graph_script(mixed))
            page.goto(url + '?case=mixed', wait_until='networkidle')
            assert page.locator('.lineage-edge.citation[data-source="chain-0"][data-target="chain-2"]').count() == 1
            # Keep cyclic relations intact rather than silently losing reachability.
            chain['settings'].pop('lineage_keep_edges')
            chain['edges'].append(citation('chain-3', 'chain-0'))
            atomic_write(site / 'assets/research-graph-data.js', graph_script(chain))
            page.goto(url + '?case=cycle', wait_until='networkidle')
            expect(page.locator('.lineage-edge')).to_have_count(7)
            # Real local route runs with the existing restrictive CSP.
            local = f"http://127.0.0.1:{server.effective_port}"
            page.route(local + '/research-flow/data.js', lambda route: route.fulfill(body=graph_script(data), content_type='application/javascript'))
            page.goto(local + '/research-lineage')
            expect(page.locator('.lineage-card')).to_have_count(7)
            page.locator('[data-node-id="d"] .lineage-info').click()
            expect(page.locator('#lineage-dialog')).to_be_visible()
            page.keyboard.press('Escape')
            expect(page.locator('[data-node-id="d"] .lineage-title')).to_have_attribute('href', '/posts/fixture-summary')
            assert not errors, errors
            assert not csp, csp
            browser.close()
            print('Timeline checks passed: reduced chains, branch preservation, exceptions, filtered bridges, citation provenance, cycles, year rows, navigation, mobile, local CSP.')
    finally:
        server.close()
