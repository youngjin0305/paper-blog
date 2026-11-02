"""Real catalog UI checks, no network, models or publication."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright, expect
from garden import ROOT

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width':1600,'height':1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto((ROOT / 'site/research-flow.html').as_uri())
    expect(page.locator('.atlas-card')).to_have_count(14)
    assert page.locator('.sidebar a[href*=research-lineage]').count() == 0
    page.locator('.atlas-title').first.click()
    expect(page.locator('#atlas-detail')).to_contain_text('이 논문이 바꾼 점')
    expect(page.locator('#atlas-detail')).to_contain_text('후속 연구')
    page.locator('.atlas-actions button').nth(0).click()
    page.locator('.atlas-actions button').nth(1).click()
    page.locator('[data-mode=compare]').click()
    expect(page.locator('.atlas-compare')).to_contain_text('출발점')
    page.locator('[data-mode=matrix]').click()
    expect(page.locator('.atlas-matrix')).to_contain_text('SPECK')
    page.get_by_role('button',name='GIMLI · 키 복구: 미확인',exact=True).click()
    expect(page.locator('#atlas-detail')).to_contain_text('연구가 없다는 결론이 아닙니다')
    with page.expect_download() as download:
        page.get_by_role('button',name='조사 메모 내려받기').click()
    assert download.value.suggested_filename == 'research-question.md'
    page.locator('#atlas-search').fill('Inception-no-match')
    expect(page.locator('#atlas-canvas')).to_contain_text('조건에 맞는 논문이 없습니다')
    page.locator('#atlas-search').fill('Pruning')
    page.locator('#atlas-search').fill('Deep Neural Networks Aiding')
    expect(page.locator('.atlas-matrix')).to_contain_text('필터 밖')
    page.locator('#atlas-search').fill('')
    page.screenshot(path=str(ROOT/'data/papers/research-matrix-preview.png'),full_page=True)
    page.locator('[data-mode=lineage]').click()
    page.screenshot(path=str(ROOT/'data/papers/research-atlas-preview.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(ROOT/'data/papers/research-mobile-preview.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
    page.locator('#atlas-topic').select_option('cryptanalysis')
    expect(page.locator('#atlas-canvas')).to_contain_text('조건에 맞는 논문이 없습니다')
    page.locator('#atlas-unclassified').check()
    assert page.locator('.atlas-card').count() > 0
    assert not errors, errors
    browser.close()
print('Research atlas browser checks passed')
