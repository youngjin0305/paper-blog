"""Optional browser verification: uses a temporary workspace and mocked research, never Gemini."""
import json
from pathlib import Path
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from garden import Garden, ROOT
from playwright.sync_api import sync_playwright
from waitress import create_server


class Source:
    def search(self, topic):
        return [{"id": "2609.00001v1", "title": "Browser test: local research pipeline", "abstract": "An offline fixture.",
                 "published": "2026-09-01T00:00:00Z", "updated": "2026-09-01T00:00:00Z", "authors": ["Test"],
                 "url": "https://arxiv.org/abs/2609.00001v1", "pdf": "https://arxiv.org/pdf/2609.00001v1"}], 1


class Summary:
    def summarize(self, *args):
        return "## 한눈에 보기\n\n브라우저 테스트용 모의 요약입니다.\n\n## 한계와 확인할 점\n\n실제 논문이 아닙니다."


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    config["schedule_enabled"] = False
    (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
    garden = Garden(root, Source(), Summary())
    server = create_server(create_app(garden), host="127.0.0.1", port=0)
    worker = threading.Thread(target=server.run, daemon=True)
    worker.start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            url = f"http://127.0.0.1:{server.effective_port}"
            page.goto(url)
            page.get_by_role("button", name="데모 글로 둘러보기").click()
            page.get_by_role("heading", name="Attention Is All You Need").wait_for()
            (ROOT / "data").mkdir(exist_ok=True)
            page.screenshot(path=str(ROOT / "data/preview-desktop.png"), full_page=True)
            page.get_by_role("link", name="Attention Is All You Need").click()
            page.get_by_role("heading", name="한눈에 보기").wait_for()
            with page.expect_download() as download:
                page.get_by_role("link", name="Markdown").click()
            assert download.value.suggested_filename.endswith(".md")
            page.goto(url + "/settings")
            page.wait_for_function("document.querySelectorAll('.topic-editor').length === 3")
            page.locator("#blog-title").fill("My research journal")
            page.get_by_role("button", name="분야 추가").click()
            editor = page.locator(".topic-editor").last
            editor.locator('[data-field="name"]').fill("양자 컴퓨팅")
            editor.locator('[data-field="id"]').fill("quantum")
            editor.locator('[data-field="query"]').fill("cat:quant-ph")
            with page.expect_navigation():
                page.get_by_role("button", name="설정 저장하기").click()
            page.wait_for_function("document.querySelectorAll('.topic-editor').length === 4")
            assert garden.config()["title"] == "My research journal"
            page.goto(url + "/topics/quantum")
            page.get_by_role("heading", name="양자 컴퓨팅", exact=True).wait_for()
            page.get_by_role("button", name="지금 논문 조사하기").click()
            page.get_by_role("heading", name="Browser test: local research pipeline").wait_for(timeout=20000)
            assert len(garden.posts("quantum")) == 1
            page.goto(url + "/settings")
            page.get_by_role("button", name="정적 블로그 내보내기").click()
            page.get_by_role("status").filter(has_text="정적 블로그를 저장했습니다").wait_for()
            assert (root / "site/index.html").exists()
            page.goto((root / "site/index.html").as_uri())
            page.get_by_role("link", name="Browser test: local research pipeline").click()
            page.get_by_role("heading", name="한눈에 보기").wait_for()
            page.goto(url)
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(ROOT / "data/preview-mobile.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile horizontal overflow"
            assert not errors, errors
            browser.close()
            print("Browser smoke passed: demo, article, download, settings, custom topic, research, static export, mobile layout. No JS errors.")
    finally:
        server.close()
