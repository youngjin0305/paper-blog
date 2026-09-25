"""Publication labels based on source metadata, never model guesses."""
import re
from urllib.parse import urlparse

PUBLICATION_FIELDS = {"journal_ref", "publication_note", "doi"}


def compact_venue(venue, archive):
    if not venue:
        return archive if archive != "원문" else "게재처 미확인"
    for full, short in (("IEEE Transactions on Information Forensics and Security", "IEEE TIFS"),
                        ("IEEE Transactions on Pattern Analysis and Machine Intelligence", "IEEE TPAMI"),
                        ("Journal of Cryptology", "J. Cryptology")):
        if full.lower() in venue.lower():
            return short
    acronym = re.search(r"\(([A-Z][A-Z0-9-]{2,14})\)", venue)
    if acronym:
        conference = re.search(r"\b([A-Z]{2,10})\s+(20\d{2})\b", venue[acronym.end():])
        return acronym[1] + (" · " + conference[0] if conference else "")
    return re.sub(r"^(?:accepted (?:at|to|for|in)|published (?:in|at)|to appear (?:in|at))\s+(?:the\s+)?", "", venue, flags=re.I)


def publication_metadata(paper):
    return {key: paper[key].strip() for key in PUBLICATION_FIELDS
            if isinstance(paper.get(key), str) and paper[key].strip()}


def publication_display(metadata):
    url = metadata.get("url") or metadata.get("source", "")
    host = urlparse(url).hostname
    archive = "arXiv" if host in ("arxiv.org", "www.arxiv.org", "export.arxiv.org") else (
        "IACR ePrint" if host == "eprint.iacr.org" else "원문")
    identifier = metadata.get("arxiv_id", "")
    if not identifier and archive != "원문":
        identifier = re.sub(r"^/(?:abs|pdf)/", "", urlparse(url).path).lstrip("/").removesuffix(".pdf")
    journal = metadata.get("journal_ref", "").strip()
    # Archive names in citation_journal_title are not peer-reviewed venues.
    if re.search(r"arxiv|eprint|cryptology.*archive", journal, re.I):
        journal = ""
    note = metadata.get("publication_note", "").strip()
    accepted = re.match(r"^(?:accepted (?:at|to|for|in)|published (?:in|at)|to appear (?:in|at))\b", note, re.I)
    venue = journal or (re.split(r"\.\s+", note, maxsplit=1)[0].rstrip(".") if accepted else "")
    label = venue if venue else (archive + " 프리프린트 · 게재처 미확인" if archive != "원문" else "게재처 미확인")
    return {"publication_label": label, "archive_label": archive, "source_id": identifier,
            "publication_short": compact_venue(venue, archive),
            "publication_note": note}
