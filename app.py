from __future__ import annotations

import argparse
import json
import logging
import secrets
import threading
import webbrowser
from pathlib import Path

import bleach
from flask import Flask, Response, abort, jsonify, render_template, request
import markdown
from markupsafe import Markup

from garden import Garden, ROOT, atomic_write


def rendered_markdown(document):
    if document.startswith("---\n"):
        parts = document.split("\n---\n", 1)
        document = parts[1] if len(parts) == 2 else document
    html = markdown.markdown(document, extensions=["tables", "fenced_code", "sane_lists"])
    tags = set(bleach.sanitizer.ALLOWED_TAGS) | {"p", "h1", "h2", "h3", "h4", "br", "hr", "pre", "code", "table", "thead", "tbody", "tr", "th", "td"}
    return Markup(bleach.clean(html, tags=tags, attributes={"a": ["href", "title"]}, protocols=["https", "http"], strip=True))


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
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.path.startswith("/api/") or response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.context_processor
    def context():
        config = garden.config()
        all_posts = garden.posts()
        counts = {topic["id"]: sum(p["topic_id"] == topic["id"] for p in all_posts) for topic in config["topics"]}
        return dict(config=config, topics=config["topics"], counts=counts, total=len(all_posts),
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
        if topic_id is not None and topic_id not in [t["id"] for t in garden.config()["topics"]]:
            return jsonify(error="존재하지 않는 분야입니다."), 400
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
    with app.test_request_context("/"):
        def page(template, depth=0, **kwargs):
            prefix = "../" * depth
            return render_template(template, config=config, topics=config["topics"], counts=counts,
                                   total=len(all_posts), token="", static_mode=True, root_url=prefix + "index.html",
                                   asset_url=prefix + "assets/", query="",
                                   topic_href=lambda i: prefix + f"topics/{i}.html",
                                   post_href=lambda i: prefix + f"posts/{i}.html", **kwargs)
        atomic_write(output / "index.html", page("index.html", posts=all_posts, selected=None))
        for topic in config["topics"]:
            atomic_write(output / "topics" / f"{topic['id']}.html", page("index.html", depth=1,
                         posts=[p for p in all_posts if p["topic_id"] == topic["id"]], selected=topic))
        for post in all_posts:
            atomic_write(output / "posts" / f"{post['id']}.html", page("post.html", depth=1, post=post,
                         source=json.loads(post["source"]), body=rendered_markdown(garden.markdown(post)), selected=None))
        atomic_write(output / "assets/style.css", (ROOT / "static/style.css").read_text(encoding="utf-8"))
        atomic_write(output / ".nojekyll", "")
    return output


def main():
    parser = argparse.ArgumentParser(description="Paper Garden — 로컬 논문 리서치 블로그")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="로컬 블로그 + 스케줄러 실행")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--open", action="store_true")
    run = commands.add_parser("run", help="지금 한 번 조사")
    run.add_argument("--topic", help="분야 ID (생략 시 활성화된 모든 분야)")
    commands.add_parser("demo", help="화면 확인용 데모 글 추가")
    commands.add_parser("export", help="site 폴더에 정적 HTML 내보내기")
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
        print("Login is not tested. Run login-gemini.cmd and choose Sign in with Google.")
    elif args.command == "export":
        print(export_site(create_app(garden), garden))
    elif args.command == "serve":
        from waitress import serve as serve_http
        garden.start_scheduler()
        url = f"http://127.0.0.1:{args.port}"
        print(f"Paper Garden: {url}\nKeep this window open for scheduled research. Ctrl+C to stop.", flush=True)
        if args.open:
            threading.Timer(1.5, lambda: webbrowser.open(url)).start()
        try:
            serve_http(create_app(garden), host="127.0.0.1", port=args.port, threads=6)
        finally:
            garden.stop.set()


if __name__ == "__main__":
    main()
