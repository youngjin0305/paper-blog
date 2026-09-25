"""Deterministic structure, provenance and numeric checks; no LLM judging."""
from decimal import Decimal
import json
import re
import unicodedata
from paper_publication import PUBLICATION_FIELDS


GROUPS = {
    "A": ["한눈에 보기", "초록", "필요성", "연구 분야 흐름", "관련 연구", "배경 지식", "문제 정의", "주요 기여"],
    "B": ["제시한 방법론"], "C": ["실험 및 평가"], "D": ["고찰", "결론"],
}
REQUIRED = ["초록", "문제 정의", "주요 기여", "제시한 방법론", "실험 및 평가", "결론"]
FIELDS = {"title", "date", "collected_at", "category", "arxiv_id", "source", "basis", "demo"}
SUMMARY_FIELDS = {"summary_model", "summarized_at"}
RUBRIC = ["relevance", "novelty", "methodology", "reproducibility"]
RANK_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": RUBRIC + ["rationale"],
    "properties": {**{key: {"type": "object", "additionalProperties": False,
        "required": ["score", "reason"], "properties": {
            "score": {"type": "integer", "minimum": 1, "maximum": 5},
            "reason": {"type": "string", "minLength": 1}}} for key in RUBRIC},
        "rationale": {"type": "string", "minLength": 1}},
}


def parse_rank(text):
    from jsonschema import validate
    result = json.loads(text)
    validate(result, RANK_SCHEMA)
    return result


def split_document(document):
    if not document.startswith("---\n") or "\n---\n" not in document[4:]:
        raise ValueError("Missing frontmatter delimiters")
    front, body = document[4:].split("\n---\n", 1)
    metadata = json.loads(front)  # Existing blog convention is JSON, a YAML subset.
    if not isinstance(metadata, dict):
        raise ValueError("Frontmatter must be an object")
    return metadata, body


def sections(body):
    # A header inside a code fence cannot satisfy a required section.
    body = re.sub(r"(?ms)^(`{3,}|~{3,})[^\n]*\n.*?^\1\s*$", "", body)
    matches = list(re.finditer(r"(?m)^## ([^\n]+)\s*$", body))
    return {m[1].strip(): body[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(body)].strip()
            for i, m in enumerate(matches)}


def numbers(text):
    text = unicodedata.normalize("NFKC", text).replace("−", "-")
    # A comma followed by whitespace separates values, not thousands. In a
    # network list such as "784-16(4)-10, 784-16(6)-10", joining "10, 784"
    # invents -10784. Also keep unspaced commas before hyphenated structures.
    text = re.sub(r"(?<=\d),(?=\d{3}(?!\d|-\d))", "", text)
    text = re.sub(r"(?<=\d)[ \t]+(?=\d{3}(?:\D|$))", "", text)
    text = re.sub(r"(?<=\d)[ \t]*\.[ \t]*(?=\d)", ".", text)
    # Percent signs and surrounding space do not change the numeric token.
    pattern = r"(?<![\d.])[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?(?!\d|\.\d)"
    return {str(Decimal(m.group()).normalize()) for m in re.finditer(pattern, text)}


def parse_references(source):
    """Copy numbered entries verbatim; unsupported author-year styles yield no entries."""
    heading = re.search(r"(?im)^\s*(?:#{1,6}\s*)?(?:\*\*)?(?:\d+\.?\s+)?(?:references|bibliography)(?:\*\*)?\s*$", source)
    if not heading:
        return {}
    tail = source[heading.end():]
    ending = re.search(r"(?im)^\s*(?:#{1,6}\s*)?(?:\*\*)?(?:appendix\b|[A-Z][. ]+Appendix\b|"
                       r"supplementary (?:material|information)\b|supplement\b|acknowledg(?:e)?ments\b)", tail)
    if ending:
        tail = tail[:ending.start()]
    found = list(re.finditer(r"(?m)^\s*(?:\[(\d+)\]|(\d+)\.)[ \t]+", tail))
    markers = []
    previous = 0
    for marker in found:
        identifier = int(marker[1] or marker[2])
        # Unbracketed numbered bibliographies proceed 1,2,... . Wrapped years/pages such
        # as '2025. pp. ...' are content of the current entry, not new citation numbers.
        if marker[2] and identifier != previous + 1:
            continue
        markers.append(marker)
        previous = identifier
    result = {}
    for i, marker in enumerate(markers):
        identifier = int(marker[1] or marker[2])
        end = markers[i + 1].start() if i + 1 < len(markers) else len(tail)
        if identifier in result:
            return {}  # Ambiguous extraction must not fabricate an association.
        result[identifier] = tail[marker.end():end].strip()
    return result


def quote_words(text):
    quoted = re.findall(r'(?m)^>\s*(.+)$|[“"]([^”"\n]+)[”"]', text)
    return sum(len((a or b).split()) for a, b in quoted)


def validate_group(group, text, source, config):
    errors = []
    present = sections(text)
    expected = GROUPS[group]
    if text.strip() and not text.lstrip().startswith("## "):
        errors.append("Group must start with an allowed H2 section")
    for name in set(present) - set(expected):
        errors.append(f"Unexpected section: {name}")
    for name in set(REQUIRED) & set(expected):
        if name == "초록" and config["abstract_mode"] == "original":
            continue
        if not present.get(name):
            errors.append(f"Missing required section: {name}")
    if group == "A":
        summary = present.get("한눈에 보기", "")
        if not re.search(r"[가-힣]", summary) or len(summary) > 400:
            errors.append("한눈에 보기 requires a short Korean topic summary (up to 400 characters)")
        if len(re.split(r"(?<=[.!?。])\s+", summary.strip())) > 2:
            errors.append("한눈에 보기 must contain only 1 or 2 sentences")
        if config["abstract_mode"] == "korean" and not re.search(r"[가-힣]", present.get("초록", "")):
            errors.append("초록 must be translated into Korean")
    if re.search(r"(?m)^# |^---\s*$", text):
        errors.append("Group must not contain a title or frontmatter")
    headers = re.findall(r"(?m)^## (.+)$", text)
    if len(headers) != len(set(headers)):
        errors.append("Duplicate section headers")
    if re.search(r"!\[|<\s*(?:img|svg|script|iframe)\b", text, re.I):
        errors.append("Images or executable HTML are forbidden")
    if group == "B" and len(present.get("제시한 방법론", "")) < config["method_min_chars"]:
        errors.append(f"제시한 방법론 requires {config['method_min_chars']} characters")
    if group == "C":
        experiment = present.get("실험 및 평가", "")
        if len(experiment) < config["experiment_min_chars"]:
            errors.append(f"실험 및 평가 requires {config['experiment_min_chars']} characters")
        missing = sorted(numbers(experiment) - numbers(source))
        if missing:
            errors.append("Numbers absent from source: " + ", ".join(missing))
    if quote_words(text) > config["max_quote_words"]:
        errors.append("Direct quotations exceed the configured word limit")
    # Catch long unattributed verbatim copying as well as explicit quotation marks.
    size = config["max_quote_words"] + 1
    source_words = source.split()
    text_words = text.split()
    source_spans = {tuple(source_words[i:i + size]) for i in range(len(source_words) - size + 1)}
    if any(tuple(text_words[i:i + size]) in source_spans for i in range(len(text_words) - size + 1)):
        errors.append("Verbatim source passage exceeds the configured word limit")
    return errors


def validate_document(document, paper, source, config):
    errors = []
    try:
        metadata, body = split_document(document)
        if set(metadata) - PUBLICATION_FIELDS not in (FIELDS, FIELDS | SUMMARY_FIELDS):
            errors.append("Frontmatter fields do not match existing posts")
        for key in PUBLICATION_FIELDS & set(metadata):
            if not isinstance(metadata[key], str):
                errors.append(f"Frontmatter {key} must be a string")
        if "summary_model" in metadata and (not isinstance(metadata["summary_model"], str) or not metadata["summary_model"].strip()):
            errors.append("Summary model must be a nonempty string")
        if metadata.get("source") != paper["url"]:
            errors.append("Frontmatter source link mismatch")
        if metadata.get("title") != paper["title"]:
            errors.append("Title must come from metadata")
        from datetime import datetime
        for name in ("date", "collected_at", *(["summarized_at"] if "summarized_at" in metadata else [])):
            if datetime.fromisoformat(metadata[name].replace("Z", "+00:00")).tzinfo is None:
                errors.append(f"Frontmatter {name} must include timezone")
        if metadata.get("basis") != "fulltext" or metadata.get("demo") is not False:
            errors.append("Incorrect fulltext frontmatter")
    except (ValueError, TypeError, KeyError) as exc:
        return [f"Frontmatter parse/shape error: {exc}"]
    if not re.search(r"(?m)^# \S", body):
        errors.append("Missing title header")
    present = sections(body)
    if config["abstract_mode"] == "korean" and numbers(present.get("초록", "")) != numbers(paper["abstract"]):
        errors.append("Translated abstract must preserve the original numeric values")
    for name in REQUIRED:
        if not present.get(name):
            errors.append("Missing required section: " + name)
    if paper["url"] not in body or paper["pdfUrl"] not in body:
        errors.append("Missing original/PDF link in body")
    for group, names in GROUPS.items():
        text = "\n\n".join("## " + name + "\n" + present[name] for name in names if name in present
                           and not (name == "초록" and config["abstract_mode"] == "original"))
        errors.extend(validate_group(group, text, source, config))
    generated = "\n".join(present.get(name, "") for names in GROUPS.values() for name in names
                          if not (name == "초록" and config["abstract_mode"] == "original"))
    if quote_words(generated) > config["max_quote_words"]:
        errors.append("Total direct quotations exceed the configured word limit")
    return errors
