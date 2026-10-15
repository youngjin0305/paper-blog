"""Public metadata and PDF retrieval; visual excerpts are handled separately."""
from datetime import datetime, timedelta
import json
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html.parser import HTMLParser
from ipaddress import ip_address
from pathlib import Path
import re
import time
import unicodedata
from urllib.parse import urlparse, unquote
import xml.etree.ElementTree as ET

import requests

from garden import Arxiv, ATOM, UTC, now, atomic_write, atomic_write_bytes
from paper_queue import canonical_id


class SourceUnavailable(RuntimeError):
    """The original PDF could not be retrieved; another paper may be tried."""


class CitationMetadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            key = attrs.get("name", attrs.get("property", "")).lower()
            self.values.setdefault(key, []).append(attrs.get("content", ""))


def identify(value):
    value = value.strip()
    if re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?", value):
        return "arxiv", canonical_id(value, "arxiv")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Use an arXiv ID or a public HTTPS paper/PDF URL")
    path = unquote(parsed.path)
    if parsed.hostname in ("arxiv.org", "www.arxiv.org", "export.arxiv.org"):
        identifier = re.sub(r"^/(?:abs|pdf)/", "", path).removesuffix(".pdf")
        return identify(identifier)
    if parsed.hostname == "eprint.iacr.org" and re.fullmatch(r"/\d{4}/\d+(?:\.pdf)?", path):
        return "eprint", "eprint:" + path[1:].removesuffix(".pdf")
    return "manual", "manual:" + sha256(value.encode()).hexdigest()[:20]


def citation_key(value):
    value = unicodedata.normalize("NFKD", value).casefold()
    return "".join(character for character in value if character.isalnum())


def public_https(value):
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return False
    try:
        address = ip_address(parsed.hostname)
    except ValueError:
        address = None
    return not (parsed.hostname == "localhost" or parsed.hostname.endswith((".local", ".localhost"))
                or (address and not address.is_global))


class Sources:
    def __init__(self, config, root=None, log=None, cache_writes=True):
        self.config = config
        self.root = Path(root) if root is not None else None
        self.last_arxiv = 0.0
        self.log = log or (lambda message: None)
        self.cache_writes = cache_writes

    def get(self, url, **kwargs):
        response = requests.get(url, timeout=self.config["http_timeout"],
                                headers={"User-Agent": "PaperGarden/1.0 personal research blog"}, **kwargs)
        response.raise_for_status()
        return response

    def arxiv(self, params):
        time.sleep(max(0, 3.1 - (time.monotonic() - self.last_arxiv)))
        self.last_arxiv = time.monotonic()
        response = self.get(self.config["arxiv_api"], params=params)
        papers, total = Arxiv.parse(response.content, datetime(1970, 1, 1, tzinfo=UTC))
        entries = ET.fromstring(response.content).findall("a:entry", ATOM)
        for paper, node in zip(papers, entries):
            paper.update(source="arxiv", pdfUrl=paper.pop("pdf"),
                         categories=[c.attrib["term"] for c in node.findall("a:category", ATOM)])
            paper["id"] = canonical_id(paper["id"], "arxiv")
        return papers, total

    def recent(self):
        current = datetime.now(UTC)
        cutoff = current - timedelta(days=7)
        terms = ["cat:" + c for c in self.config["arxiv_categories"]]
        terms += ['all:"' + k.replace('"', '') + '"' for k in self.config["keywords"]]
        if self.config.get("topic_filters"):
            # A category alone cannot widen an intersection topic to all AI/security papers.
            terms = []
            for topic, groups in self.config["topic_filters"].items():
                query = " AND ".join("(" + " OR ".join('all:"' + term.replace('"', '') + '"'
                                    for term in group) + ")" for group in groups)
                excluded = self.config.get("topic_exclusions", {}).get(topic, [])
                if excluded:
                    query += " ANDNOT (" + " OR ".join('all:"' + term.replace('"', '') + '"' for term in excluded) + ")"
                terms.append("(" + query + ")")
        papers = []
        if terms:
            query = "(" + " OR ".join(terms) + f") AND submittedDate:[{cutoff:%Y%m%d%H%M} TO {current:%Y%m%d%H%M}]"
            start = 0
            while True:
                batch, total = self.arxiv({"search_query": query, "start": start,
                    "max_results": self.config["fetch_limit"], "sortBy": "submittedDate", "sortOrder": "descending"})
                papers.extend(p for p in batch if cutoff <= datetime.fromisoformat(p["published"].replace("Z", "+00:00")) <= current)
                start += len(batch)
                if not batch or start >= total:
                    break
        if self.config["use_eprint"]:
            xml = self.get(self.config["eprint_rss"]).content
            for item in parse_eprint_feed(xml):
                published = datetime.fromisoformat(item["published"])
                if cutoff <= published <= current:
                    papers.append(item)
        return papers

    def metadata(self, value):
        source, identifier = identify(value)
        if source == "arxiv":
            papers, _ = self.arxiv({"id_list": identifier.removeprefix("arxiv:")})
            if len(papers) != 1:
                raise ValueError("arXiv ID not found")
            return papers[0]
        if source == "eprint":
            url = "https://eprint.iacr.org/" + identifier.removeprefix("eprint:")
            parser = CitationMetadata()
            parser.feed(self.get(url).text)
            values = parser.values
            def first(*keys):
                return next((values[k][0] for k in keys if values.get(k)), "")
            title = first("citation_title", "og:title")
            abstract = first("citation_abstract", "description", "og:description")
            if not title or not abstract:
                raise ValueError("ePrint metadata missing title/abstract; site format may have changed")
            published = first("article:published_time", "citation_date", "citation_publication_date").replace("/", "-")
            # ePrint citation_publication_date is often just a year; the article field has the actual date.
            if not published or re.fullmatch(r"\d{4}", published):
                raise ValueError("ePrint full publication date is unavailable")
            parsed_date = datetime.fromisoformat(published.replace("Z", "+00:00"))
            date = (parsed_date if parsed_date.tzinfo else parsed_date.replace(tzinfo=UTC)).isoformat()
            return {"id": identifier, "source": source, "title": title,
                    "journal_ref": first("citation_journal_title", "citation_conference_title"),
                    "doi": first("citation_doi"),
                    "authors": values.get("citation_author", []), "abstract": abstract,
                    "url": url, "pdfUrl": url + ".pdf", "published": date, "categories": []}
        import pymupdf
        pdf = self.download_pdf(value)
        with pymupdf.open(stream=pdf, filetype="pdf") as document:
            info = document.metadata
            text = "\n".join(page.get_text() for page in list(document)[:2])
        match = re.search(r"(?is)\babstract\b\s*[:.\-]?\s*(.+?)(?=\n\s*(?:1[. ]|introduction\b|keywords\b))", text)
        # Use embedded metadata, otherwise the first extracted line; never ask the LLM to invent it.
        title = info.get("title", "").strip() or next((line.strip() for line in text.splitlines() if line.strip()), "")
        if not title:
            raise ValueError("PDF contains neither title metadata nor extractable text")
        return {"id": identifier, "source": source, "title": title,
                "authors": [info["author"]] if info.get("author") else [], "abstract": match[1].strip() if match else "",
                "metadataQuality": "embedded" if info.get("title") and match else "partial; verify title/abstract",
                "url": value, "pdfUrl": value, "published": now(), "categories": []}

    def download_pdf(self, url):
        with self.get(url, stream=True) as response:
            data = bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data) > self.config["max_pdf_bytes"]:
                    raise ValueError("PDF exceeds max_pdf_bytes")
        if not data.startswith(b"%PDF-"):
            raise ValueError("Response is not a PDF")
        return bytes(data)

    def read_local_pdf(self, path):
        path = Path(path).expanduser()
        if not path.is_file() or path.is_symlink() or path.suffix.lower() != ".pdf":
            raise ValueError("Provide a regular local PDF file")
        if path.stat().st_size > self.config["max_pdf_bytes"]:
            raise ValueError("PDF exceeds max_pdf_bytes")
        data = path.read_bytes()
        if not data.startswith(b"%PDF-"):
            raise ValueError("Local file is not a PDF")
        import pymupdf
        with pymupdf.open(stream=data, filetype="pdf") as document:
            if not len(document):
                raise ValueError("Local PDF has no pages")
        return data

    def verify_publisher_pdf(self, data, paper):
        import pymupdf
        with pymupdf.open(stream=data, filetype="pdf") as document:
            first = citation_key(" ".join(document[index].get_text() for index in range(min(2, len(document)))))
        if not citation_key(paper["title"]) or citation_key(paper["title"]) not in first:
            raise ValueError("Publisher PDF title does not match the selected paper")
        if not paper.get("authors") or any(citation_key(name) not in first for name in paper["authors"]):
            raise ValueError("Publisher PDF authors do not match the selected paper")

    def publisher_pdf(self, paper):
        """Follow deposited DOI links only after checking the citation identity."""
        doi = paper.get("doi", "").strip()
        if not re.fullmatch(r"10\.\d{4,9}/[^\s?#]+", doi):
            raise ValueError("No verified DOI is available for a publisher PDF")
        record = self.get("https://api.crossref.org/works/" + doi).json()["message"]
        if not any(citation_key(title) == citation_key(paper["title"]) for title in record.get("title", [])):
            raise ValueError("DOI title does not match the selected paper")
        registered = {citation_key(author.get("given", "") + " " + author.get("family", ""))
                      for author in record.get("author", [])}
        if not paper.get("authors") or {citation_key(name) for name in paper["authors"]} != registered:
            raise ValueError("DOI authors do not match the selected paper")
        candidates = [link["URL"] for link in record.get("link") or []
                      if public_https(link.get("URL", "")) and "/pdf/" in link["URL"]]
        # Journals such as IACR CiC deposit a landing page, not a PDF link.
        if not candidates:
            landing = record.get("resource", {}).get("primary", {}).get("URL", "")
            if public_https(landing):
                parser = CitationMetadata()
                parser.feed(self.get(landing).text)
                values = parser.values
                if (doi.casefold() in {value.casefold() for value in values.get("citation_doi", [])}
                        and any(citation_key(title) == citation_key(paper["title"]) for title in values.get("citation_title", []))):
                    candidates = [url for url in values.get("citation_pdf_url", []) if public_https(url)]
        if not candidates:
            raise ValueError("The DOI publisher has no verified public PDF link")
        # One alternate download; no retry loops or access-control workarounds.
        url = candidates[0]
        data = self.download_pdf(url)
        self.verify_publisher_pdf(data, paper)
        return data, url

    def paper_pdf(self, paper):
        cache = None
        if self.root is not None:
            cache = self.root / self.config["archive_dir"] / sha256(paper["id"].encode()).hexdigest()[:20]
            original_manifest = cache / "downloaded-pdf.json"
            if original_manifest.exists():
                saved = json.loads(original_manifest.read_text(encoding="utf-8"))
                if all(saved.get(key) == paper.get(key) for key in ("id", "title", "authors", "pdfUrl")):
                    data = self.read_local_pdf(cache / "downloaded.pdf")
                    if sha256(data).hexdigest() != saved.get("sha256"):
                        raise ValueError("Cached original PDF checksum mismatch")
                    self.log("Using cached original PDF with matching citation and checksum")
                    return data
            manifest = cache / "publisher-pdf.json"
            if manifest.exists():
                saved = json.loads(manifest.read_text(encoding="utf-8"))
                if (saved.get("id") == paper["id"] and saved.get("title") == paper["title"]
                        and saved.get("doi") == paper.get("doi") and public_https(saved.get("url", ""))):
                    data = self.read_local_pdf(cache / "publisher.pdf")
                    if sha256(data).hexdigest() != saved.get("sha256"):
                        raise ValueError("Cached publisher PDF checksum mismatch")
                    self.verify_publisher_pdf(data, paper)
                    paper["pdfUrl"] = saved["url"]
                    self.log("Using verified cached publisher PDF")
                    return data
        try:
            data = self.download_pdf(paper["pdfUrl"])
            if cache is not None and self.cache_writes:
                atomic_write_bytes(cache / "downloaded.pdf", data)
                saved = {key: paper.get(key) for key in ("id", "title", "authors", "pdfUrl")}
                saved.update(sha256=sha256(data).hexdigest(), checkedAt=now())
                atomic_write(cache / "downloaded-pdf.json", json.dumps(saved, ensure_ascii=False, indent=2) + "\n")
            return data
        except (requests.HTTPError, requests.Timeout, requests.ConnectionError) as exc:
            status = exc.response.status_code if isinstance(exc, requests.HTTPError) and exc.response is not None else None
            host = urlparse(paper["pdfUrl"]).hostname
            detail = f"HTTP {status}" if status is not None else type(exc).__name__
            self.log(f"PDF download failed: {detail} at {host}")
            if status == 429:
                raise RuntimeError(f"PDF source returned HTTP 429 at {host}; stopped without retry") from None
            if (not self.config.get("publisher_fallback", True) or not paper.get("doi")
                    or (status is not None and status not in (403, 404, 410) and status < 500)):
                raise SourceUnavailable(f"PDF download failed ({detail} at {host}); no publisher fallback") from None
            self.log("Checking DOI publisher metadata for an alternate public PDF")
            try:
                data, url = self.publisher_pdf(paper)
            except requests.HTTPError as fallback_error:
                code = fallback_error.response.status_code if fallback_error.response is not None else "unknown"
                error = RuntimeError if code == 429 else SourceUnavailable
                raise error(f"PDF download failed ({detail} at {host}); publisher lookup/download returned HTTP {code}") from None
            except (requests.Timeout, requests.ConnectionError) as fallback_error:
                raise SourceUnavailable(f"PDF download failed ({detail} at {host}); publisher lookup/download failed ({type(fallback_error).__name__})") from None
            paper["pdfUrl"] = url
            if cache is not None and self.cache_writes:
                atomic_write_bytes(cache / "publisher.pdf", data)
                atomic_write(cache / "publisher-pdf.json", json.dumps({"id": paper["id"], "title": paper["title"],
                    "doi": paper["doi"], "url": url, "sha256": sha256(data).hexdigest(), "checkedAt": now()}, indent=2) + "\n")
            self.log("Verified publisher PDF title and authors; using alternate source")
            return data

    def local_metadata(self, metadata):
        """Require verified public citation metadata for an attached PDF."""
        if not isinstance(metadata, dict):
            raise ValueError("Local PDF metadata must be a JSON object")
        for key in ("title", "abstract", "published", "url", "pdfUrl"):
            if not isinstance(metadata.get(key), str) or not metadata[key].strip():
                raise ValueError(f"Local PDF metadata requires {key}")
        for key in ("url", "pdfUrl"):
            if not public_https(metadata[key]):
                raise ValueError(f"Local PDF {key} must be a public HTTPS URL")
            identify(metadata[key])
        published = datetime.fromisoformat(metadata["published"].replace("Z", "+00:00"))
        if published.tzinfo is None:
            raise ValueError("Local PDF published timestamp must include a timezone")
        authors = metadata.get("authors", [])
        if not isinstance(authors, list) or any(not isinstance(a, str) or not a.strip() for a in authors):
            raise ValueError("Local PDF authors must be a list of names")
        study_type = metadata.get("studyType", "empirical")
        if study_type not in ("empirical", "conceptual"):
            raise ValueError("Local PDF studyType must be empirical or conceptual")
        source, identifier = identify(metadata["url"])
        paper = {"id": identifier, "source": source, "title": metadata["title"].strip(),
                 "authors": authors, "abstract": metadata["abstract"].strip(),
                 "url": metadata["url"].strip(), "pdfUrl": metadata["pdfUrl"].strip(),
                 "published": published.isoformat(), "categories": [], "studyType": study_type}
        for key in ("journal_ref", "doi", "publication_note"):
            if key in metadata:
                if not isinstance(metadata[key], str):
                    raise ValueError(f"Local PDF metadata {key} must be a string")
                paper[key] = metadata[key].strip()
        return paper

    def fulltext(self, paper):
        import pymupdf
        import pymupdf4llm
        if paper.get("localPdf"):
            if self.root is None:
                raise ValueError("Local PDF cache requires a repository root")
            archive = (self.root / self.config["archive_dir"]).resolve()
            path = (self.root / paper["localPdf"]).resolve()
            if not path.is_relative_to(archive):
                raise ValueError("Local PDF cache path is outside archive_dir")
            data = self.read_local_pdf(path)
        else:
            data = self.paper_pdf(paper)
        self.last_pdf = data  # Exact supplied/downloaded bytes for page inspection.
        with pymupdf.open(stream=data, filetype="pdf") as document:
            markdown = pymupdf4llm.to_markdown(document, write_images=False, embed_images=False,
                                               ignore_images=True, show_progress=False)
            plain = "\n".join(page.get_text(sort=True) for page in document)
        if not markdown.strip() or not plain.strip():
            raise ValueError("PDF has no extractable text (OCR is not enabled)")
        return markdown, plain


def parse_eprint_feed(content):
    root = ET.fromstring(content)
    def local(tag):
        return tag.rsplit("}", 1)[-1]
    papers = []
    for item in root.iter():
        if local(item.tag) != "item":
            continue
        values = {}
        for child in item:
            values.setdefault(local(child.tag), []).append("".join(child.itertext()).strip())
        def first(*keys):
            return next((values[k][0] for k in keys if values.get(k)), "")
        url = first("link", "identifier").replace("http://", "https://")
        source, identifier = identify(url)
        if source != "eprint":
            continue
        date = first("date", "pubDate")
        if not date:
            continue  # A feed item without a date cannot be called a recent paper.
        try:
            published = datetime.fromisoformat(date.replace("Z", "+00:00"))
        except ValueError:
            published = parsedate_to_datetime(date)
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        abstract = first("description", "abstract")
        abstract = re.sub(r"<[^>]+>", "", abstract)
        papers.append({"id": identifier, "source": source, "url": url, "pdfUrl": url + ".pdf",
                       "title": first("title"), "authors": values.get("creator", values.get("author", [])),
                       "abstract": abstract, "published": published.isoformat(), "categories": []})
    return papers


def keyword_matches(text, term):
    # Normalize hyphenation while avoiding matches such as AI inside 'training'.
    normalize = lambda value: re.sub(r"\s+", " ", re.sub(r"[-‐‑–—]", " ", value.casefold()))
    return re.search(r"(?<!\w)" + re.escape(normalize(term)) + r"(?:s)?(?!\w)", normalize(text)) is not None


def rule_score(paper, config):
    text = paper["title"] + " " + paper["abstract"]
    keywords = [k for k in config["keywords"] if keyword_matches(text, k)]
    categories = sorted(set(config["arxiv_categories"]) & set(paper.get("categories", [])))
    topic_matches = {}
    for topic, groups in config.get("topic_filters", {}).items():
        if any(keyword_matches(text, term) for term in config.get("topic_exclusions", {}).get(topic, [])):
            continue
        matches = [[term for term in group if keyword_matches(text, term)] for group in groups]
        if all(matches):
            topic_matches[topic] = [term for group in matches for term in group]
    if config.get("topic_filters"):
        if not topic_matches:
            return 0, {"keywords": [], "categories": categories, "score": 0, "topic": None}
        topic = max(topic_matches, key=lambda name: len(topic_matches[name]))
        keywords = topic_matches[topic]
        score = min(5.0, len(keywords) + len(categories))
        return score, {"keywords": keywords, "categories": categories, "score": score,
                       "topic": topic, "topicMatches": topic_matches}
    score = min(5.0, len(keywords) + 2 * len(categories))
    return score, {"keywords": keywords, "categories": categories, "score": score}
