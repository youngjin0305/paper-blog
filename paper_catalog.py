"""Verified reading lists and essential-paper annotations shared by CLI and Pages."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
from urllib.parse import urlparse

from paper_queue import entry, ordered


def load_catalog(root, config):
    relative = config.get("core_catalog_path", "data/core-papers.json")
    path = (Path(root) / relative).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError("Core catalog must be within the repository")
    if not path.exists():
        return {"version": 1, "criteria": "", "papers": []}
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(catalog, dict) or catalog.get("version") != 1 or not isinstance(catalog.get("papers"), list):
        raise ValueError("Invalid core paper catalog")
    ids = set()
    for paper in catalog["papers"]:
        from paper_sources import Sources
        verified = Sources({}).local_metadata(paper)
        if paper.get("id") != verified["id"] or paper.get("source") != verified["source"]:
            raise ValueError("Core paper ID/source must match its verified URL")
        for key in ("id", "title", "abstract", "published", "url", "pdfUrl", "topic_id", "coreRationale", "coreBasis"):
            if not isinstance(paper.get(key), str) or not paper[key].strip():
                raise ValueError("Core paper requires " + key)
        if paper["id"] in ids or paper.get("source") not in ("arxiv", "eprint", "manual"):
            raise ValueError("Duplicate/invalid core paper ID or source")
        ids.add(paper["id"])
        if paper.get("essential") is not True or not isinstance(paper.get("authors"), list) or not paper["authors"] or any(
            not isinstance(author, str) or not author.strip() for author in paper["authors"]
        ):
            raise ValueError("Core paper requires verified authors and essential flag")
        if datetime.fromisoformat(paper["published"].replace("Z", "+00:00")).tzinfo is None:
            raise ValueError("Core paper date requires timezone")
        citation = paper.get("citation", {})
        links = [paper["url"], paper["pdfUrl"], *[item["url"] for item in paper.get("evidence", [])], citation.get("url", "")]
        if not paper.get("evidence") or any(urlparse(url).scheme != "https" or not urlparse(url).hostname
                                              or urlparse(url).username or urlparse(url).password for url in links):
            raise ValueError("Core papers require public HTTPS evidence and paper links")
        if not citation or (type(citation.get("count")) is not int or citation["count"] < 0
                         or citation.get("source") != "Crossref" or not citation.get("checkedAt")):
            raise ValueError("Citation count requires source and checked date")
    return catalog


def seed_core(queue, papers, timestamp, reset_pending=False):
    """Keep publication/seen history; pin curated papers in the supplied reading order."""
    if reset_pending:
        for paper in queue["papers"]:
            if paper["status"] in ("candidate", "pinned", "failed"):
                paper.update(status="expired", expirationReason="Reading list reset by user", expiredAt=timestamp)
    existing = {paper["id"]: paper for paper in queue["papers"]}
    base = datetime.fromisoformat(timestamp)
    for index, verified in enumerate(papers):
        paper = existing.get(verified["id"])
        if paper is None:
            paper = entry(verified, "pinned", (base + timedelta(microseconds=index)).isoformat())
            queue["papers"].append(paper)
            existing[paper["id"]] = paper
        elif paper["status"] not in ("done", "pinned"):
            paper.update(deepcopy(verified))
            paper.update(status="pinned", addedAt=(base + timedelta(microseconds=index)).isoformat(), weeksInQueue=0)
            paper.pop("expirationReason", None)
            paper.pop("expiredAt", None)
        paper.update({key: deepcopy(verified[key]) for key in
                      ("essential", "coreRationale", "coreBasis", "evidence", "citation") if key in verified})
        if paper["id"] not in queue["seen"]:
            queue["seen"].append(paper["id"])
    return ordered(queue)


def reading_library(root, config, posts, essentials=False):
    pipeline = config.get("pipeline", {})
    catalog = load_catalog(root, pipeline)
    path = Path(root) / pipeline.get("queue_path", "data/paper-queue.json")
    queue = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"papers": []}
    states = {paper["id"]: paper for paper in queue["papers"]}
    core = {paper["id"]: paper for paper in catalog["papers"]}
    items = catalog["papers"] if essentials else ordered(queue)
    published = {source_key(json.loads(post["source"])["url"]): post for post in posts}
    status_names = {"pinned": "우선 정리 대기", "candidate": "정리 대기", "done": "정리 완료",
                    "failed": "검증 실패 · 초안", "expired": "대기 종료"}
    result = []
    for item in items:
        paper = {**item, **core.get(item["id"], {})}
        state = states.get(paper["id"], {})
        post = next((post for post in posts if post["path"] == state.get("postPath")), None)
        post = post or published.get(source_key(paper["url"]))
        status = "done" if post else state.get("status", "candidate")
        result.append({**paper, "status": status, "status_label": status_names[status],
                       "summary_id": post["id"] if post else None})
    return result, catalog.get("criteria", "")


def annotate_posts(posts, catalog):
    by_url = {source_key(paper["url"]): paper for paper in catalog["papers"]}
    for post in posts:
        paper = by_url.get(source_key(json.loads(post["source"])["url"]))
        post["essential"] = bool(paper)
        if paper:
            post["coreRationale"] = paper["coreRationale"]
    return posts


def source_key(url):
    from paper_sources import identify
    try:
        return identify(url)[1]
    except ValueError:
        return url.rstrip("/")
