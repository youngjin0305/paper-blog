from __future__ import annotations

import argparse
from html import escape
import json
import logging
import secrets
import threading
import uuid
import webbrowser
from pathlib import Path

import bleach
from flask import Flask, Response, abort, jsonify, render_template, request
import markdown
from markupsafe import Markup

from garden import Garden, ROOT, atomic_write, atomic_write_bytes, grouped_topics, normalize_search
from paper_math import math_spans
from paper_catalog import reading_library
from paper_graph import build_graph, sync_graph_evidence


def rendered_markdown(document):
    if document.startswith("---\n"):
        parts = document.split("\n---\n", 1)
        document = parts[1] if len(parts) == 2 else document
    spans, _ = math_spans(document)
    marker_prefix = "MATHPLACEHOLDER" + uuid.uuid4().hex.upper() + "X"
    markers = {}
    if spans:
        chunks, offset = [], 0
        for index, span in enumerate(spans):
            marker = marker_prefix + str(index) + "END"
            chunks.extend((document[offset:span.start], marker))
            markers[marker] = document[span.start:span.end]
            offset = span.end
        document = "".join(chunks) + document[offset:]
    html = markdown.markdown(document, extensions=["tables", "fenced_code", "sane_lists"])
    tags = set(bleach.sanitizer.ALLOWED_TAGS) | {"p", "h1", "h2", "h3", "h4", "br", "hr", "pre", "code", "table", "thead", "tbody", "tr", "th", "td"}
    safe = bleach.clean(html, tags=tags, attributes={"a": ["href", "title"]}, protocols=["https", "http"], strip=True)
    for marker, original in markers.items():
        safe = safe.replace(marker, escape(original, quote=True))
    return Markup(safe)


def create_app(garden=None):
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=128 * 1024, TRUSTED_HOSTS=["localhost", "127.0.0.1", "[::1]"])
    garden = garden or Garden()
    app.config["GARDEN"] = garden
    token = secrets.token_urlsafe(32)

    @app.before_request
    def protect_local_writes():
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            if not secrets.compare_digest(request.headers.get("X-Garden-Token", ""), token):
                return jsonify(error="잘못된 요청입니다. 페이지를 새로고침하세요."), 403
            if not request.is_json:
                return jsonify(error="JSON 요청이 필요합니다."), 415

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        # KaTeX positions glyphs with inline style attributes; keep the
        # exception limited to article HTML, while stylesheets remain local.
        math_style = "style-src-attr 'unsafe-inline'; " if request.path.startswith("/posts/") and response.mimetype == "text/html" else ""
        response.headers["Content-Security-Policy"] = ("default-src 'self'; script-src 'self'; style-src 'self'; "
                                                       + math_style + "img-src 'self' data:; connect-src 'self'; "
                                                       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if request.path.startswith("/api/") or response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.context_processor
    def context():
        config = garden.config()
        all_posts = garden.posts()
        counts = {topic["id"]: sum(p["topic_id"] == topic["id"] for p in all_posts) for topic in config["topics"]}
        reading, _ = reading_library(garden.root, config, all_posts)
        essentials, _ = reading_library(garden.root, config, all_posts, essentials=True)
        return dict(config=config, topics=config["topics"], counts=counts, total=len(all_posts),
                    topic_groups=grouped_topics(config["topics"]), pending_count=len(reading), essential_count=len(essentials),
                    reading_href="/reading-list", essential_href="/essentials",
                    graph_href="/research-flow",
                    token=token, static_mode=False, root_url="/", asset_url="/static/",
                    topic_href=lambda identifier: f"/topics/{identifier}",
                    post_href=lambda identifier: f"/posts/{identifier}")

    @app.get("/")
    def index():
        return render_template("index.html", posts=garden.posts(query=request.args.get("q", "")), selected=None,
                               query=request.args.get("q", ""))

    @app.get("/topics/<identifier>")
    def topic_page(identifier):
        topic = next((t for t in garden.config()["topics"] if t["id"] == identifier), None)
        if not topic:
            abort(404)
        return render_template("index.html", posts=garden.posts(identifier, request.args.get("q", "")),
                               selected=topic, query=request.args.get("q", ""))

    @app.get("/posts/<identifier>")
    def post_page(identifier):
        post = garden.post(identifier)
        if not post:
            abort(404)
        try:
            body = rendered_markdown(garden.markdown(post))
        except FileNotFoundError:
            return "Markdown 파일을 찾을 수 없습니다. content 폴더의 원본을 복원하세요.", 404
        return render_template("post.html", post=post, body=body, source=json.loads(post["source"]), selected=None)

    @app.get("/reading-list")
    @app.get("/essentials")
    def reading_page():
        essentials = request.path == "/essentials"
        config = garden.config()
        papers, criteria = reading_library(garden.root, config, garden.posts(), essentials)
        query, category = request.args.get("q", ""), request.args.get("category", "")
        if category and category not in {t["id"] for t in config["topics"]}:
            abort(404)
        terms = normalize_search(query).split()
        papers = [p for p in papers if (not category or p["topic_id"] == category)
                  and all(term in normalize_search(" ".join([p["title"], *p.get("authors", []), p.get("coreRationale", ""), p["abstract"]])) for term in terms)]
        return render_template("reading.html", selected=None, papers=papers, essential_view=essentials,
                               criteria=criteria, query=query, category=category, reading_view=True)

    @app.get("/research-flow")
    def graph_page():
        return render_template("graph.html", selected=None, graph_view=True, graph_data_url="/research-flow/data.js")

    @app.get("/research-flow/data.js")
    def graph_data():
        graph = build_graph(garden.root, garden.config(), garden.posts())
        return Response(graph_script(graph), mimetype="application/javascript", headers={"Cache-Control": "no-store"})

    @app.get("/posts/<identifier>/markdown")
    def download(identifier):
        post = garden.post(identifier)
        if not post:
            abort(404)
        try:
            return Response(garden.markdown(post), mimetype="text/markdown", headers={"Content-Disposition": f'attachment; filename="{identifier}.md"'})
        except FileNotFoundError:
            abort(404)

    @app.get("/settings")
    def settings():
        return render_template("settings.html", selected=None)

    @app.get("/api/config")
    def get_config():
        return jsonify(garden.config())

    @app.post("/api/config")
    def save_config():
        try:
            return jsonify(garden.save_config(request.get_json()))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400

    @app.get("/api/status")
    def status():
        return jsonify(garden.status())

    @app.post("/api/research")
    def research():
        payload = request.get_json()
        if not isinstance(payload, dict):
            return jsonify(error="올바른 JSON 객체를 보내세요."), 400
        topic_id = payload.get("topic_id")
        topics = {t["id"]: t for t in garden.config()["topics"]}
        if topic_id is not None and topic_id not in topics:
            return jsonify(error="존재하지 않는 분야입니다."), 400
        if topic_id is not None and not topics[topic_id]["enabled"]:
            return jsonify(error="분류 전용 분야는 논문을 조사하지 않습니다."), 400
        if not garden.launch(topic_id):
            return jsonify(error="이미 조사 중입니다. 완료 후 다시 실행하세요."), 409
        return jsonify(message="조사를 시작했습니다. 실행 기록에서 진행 상황을 확인하세요."), 202

    @app.post("/api/demo")
    def demo():
        garden.seed_demo()
        return jsonify(message="데모 글을 추가했습니다.")

    @app.post("/api/export")
    def export():
        path = export_site(app, garden)
        return jsonify(message=f"정적 블로그를 저장했습니다: {path}")

    return app


def export_site(app, garden):
    """Relative links work both on disk and beneath a future project-site prefix."""
    output = garden.root / "site"
    all_posts = garden.posts()
    config = garden.config()
    counts = {t["id"]: sum(p["topic_id"] == t["id"] for p in all_posts) for t in config["topics"]}
    reading, criteria = reading_library(garden.root, config, all_posts)
    essentials, _ = reading_library(garden.root, config, all_posts, essentials=True)
    with app.test_request_context("/"):
        def page(template, depth=0, **kwargs):
            prefix = "../" * depth
            return render_template(template, config=config, topics=config["topics"], counts=counts,
                                   total=len(all_posts), token="", static_mode=True, root_url=prefix + "index.html",
                                   topic_groups=grouped_topics(config["topics"]), pending_count=len(reading), essential_count=len(essentials),
                                   reading_href=prefix + "reading-list.html", essential_href=prefix + "essentials.html",
                                   graph_href=prefix + "research-flow.html",
                                   asset_url=prefix + "assets/", query="",
                                   topic_href=lambda i: prefix + f"topics/{i}.html",
                                   post_href=lambda i: prefix + f"posts/{i}.html", **kwargs)
        atomic_write(output / "index.html", page("index.html", posts=all_posts, selected=None))
        atomic_write(output / "research-flow.html", page("graph.html", selected=None, graph_view=True,
                     graph_data_url="assets/research-graph-data.js"))
        atomic_write(output / "assets/research-graph-data.js", graph_script(build_graph(garden.root, config, all_posts)))
        atomic_write(output / "assets/research-graph.js", (ROOT / "static/research-graph.js").read_text(encoding="utf-8"))
        for name, papers, essential_view in (("reading-list", reading, False), ("essentials", essentials, True)):
            atomic_write(output / (name + ".html"), page("reading.html", papers=papers, criteria=criteria,
                         essential_view=essential_view, selected=None, category="", reading_view=True))
        for topic in config["topics"]:
            atomic_write(output / "topics" / f"{topic['id']}.html", page("index.html", depth=1,
                         posts=[p for p in all_posts if p["topic_id"] == topic["id"]], selected=topic))
        for post in all_posts:
            atomic_write(output / "posts" / f"{post['id']}.html", page("post.html", depth=1, post=post,
                         source=json.loads(post["source"]), body=rendered_markdown(garden.markdown(post)), selected=None))
        atomic_write(output / "assets/style.css", (ROOT / "static/style.css").read_text(encoding="utf-8"))
        search_index = {post["id"]: garden.search_text(post) for post in all_posts}
        search_index.update({"reading:" + p["id"]: normalize_search(" ".join([p["title"], *p.get("authors", []),
                            p.get("coreRationale", ""), p["abstract"]])) for p in [*reading, *essentials]})
        search_json = json.dumps(search_index, ensure_ascii=False, separators=(",", ":"))
        search_json = search_json.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        atomic_write(output / "assets/search-data.js", "window.paperSearchIndex = " + search_json + ";\n")
        atomic_write(output / "assets/search.js", (ROOT / "static/search.js").read_text(encoding="utf-8"))
        atomic_write(output / "assets/math.js", (ROOT / "static/math.js").read_text(encoding="utf-8"))
        for asset in (ROOT / "static/vendor/katex").rglob("*"):
            if asset.is_file():
                atomic_write_bytes(output / "assets/vendor/katex" / asset.relative_to(ROOT / "static/vendor/katex"), asset.read_bytes())
        atomic_write(output / ".nojekyll", "")
    return output


def graph_script(graph):
    encoded = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
    return "window.researchGraph = " + encoded.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029") + ";\n"


def main():
    parser = argparse.ArgumentParser(description="Paper Blog — 로컬 논문 리서치 블로그")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="로컬 블로그 + 스케줄러 실행")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--open", action="store_true")
    run = commands.add_parser("run", help="지금 한 번 조사")
    run.add_argument("--topic", help="분야 ID (생략 시 활성화된 모든 분야)")
    commands.add_parser("demo", help="화면 확인용 데모 글 추가")
    commands.add_parser("export", help="site 폴더에 정적 HTML 내보내기")
    graph_sync = commands.add_parser("graph-sync", help="공개 참고문헌과 필수 논문의 인용 관계 갱신 (모델 호출 없음)")
    graph_sync.add_argument("--dry-run", action="store_true", help="인용 근거 파일을 저장하지 않음")
    commands.add_parser("check", help="설정 및 CLI 설치 상태 확인 (모델 호출 없음)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    garden = Garden()
    if args.command == "run":
        statuses = garden.research(args.topic)
        print(json.dumps(garden.status()["runs"], ensure_ascii=False, indent=2))
        raise SystemExit(1 if any(s != "success" for s in statuses) else 0)
    if args.command == "demo":
        garden.seed_demo()
        print("Demo ready.")
    elif args.command == "check":
        garden.config()
        print(json.dumps(garden.status(), ensure_ascii=False, indent=2))
        print("Login is not tested. Gemini: login-gemini.cmd; Codex: codex login; Claude: claude.")
    elif args.command == "export":
        print(export_site(create_app(garden), garden))
    elif args.command == "graph-sync":
        result = sync_graph_evidence(garden.root, garden.config(), garden.posts(), args.dry_run)
        print(json.dumps({"citation_edges": len(result["edges"]), "warnings": result["warnings"], "dry_run": args.dry_run}, ensure_ascii=False))
    elif args.command == "serve":
        from waitress import serve as serve_http
        garden.start_scheduler()
        url = f"http://127.0.0.1:{args.port}"
        print(f"{garden.config()['title']}: {url}\nKeep this window open for scheduled research. Ctrl+C to stop.", flush=True)
        if args.open:
            threading.Timer(1.5, lambda: webbrowser.open(url)).start()
        try:
            serve_http(create_app(garden), host="127.0.0.1", port=args.port, threads=6)
        finally:
            garden.stop.set()


if __name__ == "__main__":
    main()
