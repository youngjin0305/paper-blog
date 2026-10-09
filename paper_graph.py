"""Build a reproducible research map without model-generated citation claims."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlparse


DEFAULTS = {"evidence_path": "data/paper-graph-evidence.json", "recommended_score": 3.5,
            "recommended_relevance": 4, "similarity_threshold": 0.12, "max_related_parents": 2, "max_nodes": 60, "concepts": []}
STOP = set("the and for with from that this which into using based paper propose proposed method methods model models learning neural deep study results research analysis approach show images image cipher cryptanalysis detection data our are can has have use used new these their through not performance training network networks security attack attacks".split())


def validate_graph_settings(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError("Unknown research_graph setting")
    config = {**deepcopy(DEFAULTS), **value}
    if not isinstance(config["evidence_path"], str):
        raise ValueError("Graph evidence path must be a string")
    path = Path(config["evidence_path"])
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("Graph evidence path must be repository-relative")
    for key, low, high in (("recommended_score", 0, 5), ("recommended_relevance", 1, 5),
                           ("similarity_threshold", 0.01, 1), ("max_related_parents", 1, 5), ("max_nodes", 1, 300)):
        item = config[key]
        if type(item) not in (int, float) or not low <= item <= high:
            raise ValueError("Invalid research_graph." + key)
    if any(type(config[key]) is not int for key in ("max_related_parents", "recommended_relevance", "max_nodes")):
        raise ValueError("Graph parent/relevance limits must be integers")
    if not isinstance(config["concepts"], list):
        raise ValueError("Graph concepts must be a list")
    ids = set()
    for concept in config["concepts"]:
        if (not isinstance(concept, dict) or not isinstance(concept.get("id"), str) or concept["id"] in ids
                or not isinstance(concept.get("label"), str) or not concept["label"].strip()
                or not isinstance(concept.get("keywords"), list) or not concept["keywords"]
                or any(not isinstance(k, str) or not k.strip() for k in concept["keywords"])):
            raise ValueError("Invalid graph concept")
        ids.add(concept["id"])
    return config


def compact(text):
    return re.sub(r"[\W_]", "", unicodedata.normalize("NFKC", text).casefold())


def reference_tail(text):
    heading = re.search(r"(?im)^\s*(?:#{1,6}\s*)?(?:\*\*)?(?:\d+\.?\s+)?(?:references|bibliography)(?:\*\*)?\s*$", text)
    if not heading:
        return ""
    tail = text[heading.end():]
    ending = re.search(r"(?im)^\s*(?:#{1,6}\s*)?(?:appendix\b|supplementary\b|acknowledg(?:e)?ments\b)", tail)
    return tail[:ending.start()] if ending else tail


def match_reference_rows(citing, rows, papers, evidence_url, origin, checked_at):
    """Only a deposited reference DOI or full title match can create a citation."""
    found = {}
    for row in rows:
        text = row if isinstance(row, str) else " ".join(str(row.get(k, "")) for k in ("article-title", "unstructured"))
        doi = str(row.get("DOI", "")).casefold() if isinstance(row, dict) else ""
        normalized = compact(text)
        for paper in papers:
            if paper["id"] == citing["id"]:
                continue
            title = compact(paper["title"])
            exact_doi = doi and paper.get("doi") and doi == paper["doi"].casefold()
            if not exact_doi and not (len(title) >= 16 and title in normalized):
                continue
            excerpt = text
            words = re.findall(r"\w+", paper["title"])
            location = re.search(r"\W*".join(re.escape(w) for w in words), text, re.I) if words else None
            if location:
                excerpt = text[max(0, location.start() - 40):location.end() + 60]
            elif exact_doi:
                excerpt = "DOI: " + doi
            else:
                excerpt = "일치한 제목: " + paper["title"]
            found[paper["id"]] = {"citedId": paper["id"], "evidence": {
                "url": evidence_url, "origin": origin, "match": "DOI" if exact_doi else "title",
                "excerpt": re.sub(r"\s+", " ", excerpt).strip()[:220], "checkedAt": checked_at}}
    return list(found.values())


def references_from_text(citing, text, papers, checked_at):
    tail = reference_tail(text)
    if not tail:
        return []
    # Preserve complete wrapped titles. The excerpt is a short locating aid.
    return match_reference_rows(citing, [tail], papers, citing["pdfUrl"], "original-references", checked_at)


def graph_papers(root, config, posts):
    from paper_catalog import load_catalog, source_key
    from paper_validation import split_document
    pipeline = config.get("pipeline", {})
    path = Path(root) / pipeline.get("queue_path", "data/paper-queue.json")
    queue = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"papers": []}
    states = {p["id"]: p for p in queue["papers"]}
    papers = {p["id"]: deepcopy(p) for p in queue["papers"] if p["status"] in ("candidate", "pinned", "done")}
    for p in load_catalog(root, pipeline)["papers"]:
        papers[p["id"]] = {**states.get(p["id"], {}), **p}
    for post in posts:
        if post["demo"] or post.get("basis") != "fulltext":
            continue
        metadata, body = split_document((Path(root) / post["path"]).read_text(encoding="utf-8"))
        url = json.loads(post["source"])["url"]
        identifier = source_key(url)
        paper = papers.setdefault(identifier, {"id": identifier, "title": post["title"], "url": url,
                                              "published": post["published"], "topic_id": post["topic_id"]})
        abstract = re.search(r"(?ms)^## 초록\s*\n(.*?)(?=^## |\Z)", body)
        paper.update({"summary_id": post["id"], "summary_basis": "fulltext", "status": "done",
                      "authors": post.get("authors", []), "abstract": paper.get("abstract") or (abstract[1] if abstract else "")})
        for key in ("doi", "journal_ref", "publication_note"):
            if metadata.get(key):
                paper[key] = metadata[key]
    return list(papers.values())


def tokens(paper):
    text = (paper["title"] + " ") * 3 + paper.get("abstract", "")
    words = re.findall(r"[a-z][a-z0-9]{2,}", unicodedata.normalize("NFKC", text).casefold())
    return Counter(w for w in words if w not in STOP)


def build_graph(root, config, posts):
    from paper_sources import keyword_matches, rule_score
    from paper_publication import publication_display
    from paper_config import validate_pipeline
    pipeline = validate_pipeline(config.get("pipeline", {}))
    settings = validate_graph_settings(config.get("research_graph", {}))
    papers = graph_papers(root, config, posts)
    topics = {t["id"]: t for t in config["topics"]}
    nodes, counts = [], [tokens(p) for p in papers]
    frequencies = Counter(w for count in counts for w in count)
    vectors = [{w: (1 + math.log(n)) * math.log(1 + len(papers) / frequencies[w]) for w, n in count.items()} for count in counts]
    norms = [math.sqrt(sum(v * v for v in vector.values())) for vector in vectors]
    for paper in papers:
        topic = topics.get(paper["topic_id"], {"name": paper["topic_id"], "group": "Other"})
        score = paper.get("score", 0)
        relevance = paper.get("scoreDetail", {}).get("llm", {}).get("relevance", {}).get("score", 0)
        core = bool(paper.get("essential"))
        publication = publication_display(paper)
        venue = publication["publication_label"] != "게재처 미확인" and "프리프린트" not in publication["publication_label"]
        filters = pipeline["topic_filters"]
        in_scope = core or paper["topic_id"] not in filters or rule_score(paper, pipeline)[1].get("topic") == paper["topic_id"]
        recommended = core or (in_scope and (venue or (bool(paper.get("summary_id")) and score >= settings["recommended_score"] and relevance >= settings["recommended_relevance"])))
        text = paper["title"] + " " + paper.get("abstract", "")
        concepts = [c for c in settings["concepts"] if any(keyword_matches(text, k) for k in c["keywords"])]
        year = int(paper.get("publicationYear") or paper["published"][:4])
        published_stamp = datetime.fromisoformat(paper["published"].replace("Z", "+00:00"))
        if published_stamp.tzinfo is None:
            published_stamp = published_stamp.replace(tzinfo=timezone.utc)
        nodes.append({"id": paper["id"], "title": paper["title"], "authors": paper.get("authors", []),
                      "year": year, "date": paper["published"], "timeOrder": published_stamp.timestamp(),
                      "datePrecision": paper.get("publishedPrecision", "day"), "topic": paper["topic_id"], "topicLabel": topic["name"],
                      "group": topic.get("group") or "Other", "core": core, "summaryId": paper.get("summary_id"),
                      "url": paper["url"], "venue": publication["publication_label"], "venueConfirmed": venue,
                      "recommended": recommended, "inScope": in_scope, "score": score, "relevance": relevance,
                      "concepts": [c["id"] for c in concepts], "conceptLabels": [c["label"] for c in concepts],
                      "qualityReason": "필수 논문" if core else ("현재 수집 범위 밖의 기존 기록" if not in_scope else
                      ("출처 메타데이터에서 게재처 확인" if venue else ("전문 정리 완료 · 관련성/선정 점수 기준 충족" if recommended else "게재처 또는 선정 점수 기준 미충족"))),
                      "status": "정리 완료" if paper.get("summary_id") else (
                          "검증 실패 · 초안" if paper.get("status") == "failed" else "수집 · 정리 대기")})
    by_id = {node["id"]: node for node in nodes}
    path = (Path(root) / settings["evidence_path"]).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError("Graph evidence must be within repository")
    snapshot = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"edges": [], "checkedAt": None}
    edges = {}
    for citing in papers:
        for ref in citing.get("graphReferences", []):
            edge = {"source": ref["citedId"], "target": citing["id"], "kind": "citation", "evidence": ref["evidence"]}
            edges[(edge["source"], edge["target"])] = edge
    for edge in snapshot["edges"]:
        edges.setdefault((edge["source"], edge["target"]), edge)
    edges = {pair: edge for pair, edge in edges.items() if pair[0] in by_id and pair[1] in by_id and pair[0] != pair[1]
             and edge.get("kind") == "citation" and urlparse(edge.get("evidence", {}).get("url", "")).scheme == "https"}
    for i, newer in enumerate(nodes):
        candidates = []
        for j, older in enumerate(nodes):
            if older["year"] > newer["year"]:
                continue
            if older["year"] == newer["year"] and (older["datePrecision"] != "day" or newer["datePrecision"] != "day" or older["timeOrder"] >= newer["timeOrder"]):
                continue
            if older["group"] != newer["group"] or not (older["core"] or older["summaryId"]):
                continue
            if (older["id"], newer["id"]) in edges:
                continue
            shared = set(older["concepts"]) & set(newer["concepts"])
            similarity = sum(v * vectors[j].get(w, 0) for w, v in vectors[i].items()) / (norms[i] * norms[j]) if norms[i] and norms[j] else 0
            if shared and similarity >= settings["similarity_threshold"]:
                candidates.append((similarity, older, shared))
        for similarity, older, shared in sorted(candidates, key=lambda c: (-c[0], c[1]["id"]))[:settings["max_related_parents"]]:
            labels = [c["label"] for c in settings["concepts"] if c["id"] in shared]
            edges[(older["id"], newer["id"])] = {"source": older["id"], "target": newer["id"], "kind": "related",
                "similarity": round(similarity, 3), "reason": "공통 개념: " + ", ".join(labels) + "; 제목·초록 TF-IDF 유사도. 실제 인용 또는 계승을 뜻하지 않습니다."}
    return {"version": 1, "nodes": nodes, "edges": sorted(edges.values(), key=lambda e: (e["target"], e["source"])),
            "checkedAt": snapshot.get("checkedAt"), "settings": settings}


def sync_graph_evidence(root, config, posts, dry_run=False):
    """Fetch public deposited references and core-paper PDFs; never invoke an LLM."""
    import requests
    import pymupdf
    from garden import atomic_write, now
    from paper_sources import Sources
    from paper_config import validate_pipeline
    settings = validate_graph_settings(config.get("research_graph", {}))
    pipeline = validate_pipeline(config.get("pipeline", {}))
    papers = graph_papers(root, config, posts)
    edges, warnings = {}, []
    stamp = now()
    source = Sources(pipeline, root=root)
    for citing in papers:
        refs = []
        doi = citing.get("doi")
        if doi:
            api = "https://api.crossref.org/works/" + doi
            try:
                response = requests.get(api, headers={"User-Agent": "PaperBlog/1.0 reference map"}, timeout=20)
                response.raise_for_status()
                refs += match_reference_rows(citing, response.json()["message"].get("reference", []), papers, api, "crossref-references", stamp)
            except (requests.RequestException, ValueError, KeyError):
                warnings.append({"paperId": citing["id"], "source": "Crossref", "reason": "Reference metadata unavailable"})
        archive = Path(root) / pipeline["archive_dir"] / hashlib.sha256(citing["id"].encode()).hexdigest()[:20] / "source.txt"
        plain = archive.read_text(encoding="utf-8") if archive.exists() else ""
        if not plain and citing.get("essential") and not refs:
            try:
                pdf = source.download_pdf(citing["pdfUrl"])
                with pymupdf.open(stream=pdf, filetype="pdf") as document:
                    plain = "\n".join(page.get_text(sort=True) for page in document)
            except (requests.RequestException, ValueError, RuntimeError):
                warnings.append({"paperId": citing["id"], "source": "PDF", "reason": "Reference text unavailable"})
        if plain:
            refs += references_from_text(citing, plain, papers, stamp)
        markdown_path = archive.with_name("source.md")
        if markdown_path.exists():
            refs += references_from_text(citing, markdown_path.read_text(encoding="utf-8"), papers, stamp)
        for ref in refs:
            pair = (ref["citedId"], citing["id"])
            edges.setdefault(pair, {"source": pair[0], "target": pair[1], "kind": "citation", "evidence": ref["evidence"]})
    snapshot = {"version": 1, "checkedAt": stamp, "edges": sorted(edges.values(), key=lambda e: (e["target"], e["source"])), "warnings": warnings}
    if not dry_run:
        # Keep previously verified links when a source is temporarily unavailable.
        path = (Path(root) / settings["evidence_path"]).resolve()
        if not path.is_relative_to(Path(root).resolve()):
            raise ValueError("Graph evidence must be within repository")
        if path.exists():
            previous = json.loads(path.read_text(encoding="utf-8"))
            for edge in previous.get("edges", []):
                edges.setdefault((edge["source"], edge["target"]), edge)
            snapshot["edges"] = sorted(edges.values(), key=lambda e: (e["target"], e["source"]))
        atomic_write(path, json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    return snapshot
