"""Validation for the pipeline section of the existing config.json."""
from copy import deepcopy
from pathlib import Path


DEFAULTS = {
    "keywords": ["large language model", "cryptography", "retrieval"],
    "arxiv_categories": ["cs.AI", "cs.CL", "cs.CR"], "use_eprint": True,
    "weekly_new": 10, "pool_limit": 20, "expiry_weeks": 3, "llm_shortlist": 30,
    "method_min_chars": 1200, "experiment_min_chars": 1000,
    "post_dir": "content/ai", "category": "ai", "queue_path": "data/paper-queue.json",
    "draft_dir": "drafts", "archive_dir": "data/papers", "log_dir": "logs",
    "agy_path": "agy", "model": "", "timeout": 300, "http_timeout": 60,
    "max_pdf_bytes": 52428800, "rule_weight": 0.3, "llm_weight": 0.7,
    "abstract_mode": "original", "max_quote_words": 25,
    "arxiv_api": "https://export.arxiv.org/api/query",
    "eprint_rss": "https://eprint.iacr.org/rss/rss.xml", "fetch_limit": 200,
}


def validate_pipeline(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError("Unknown pipeline setting or non-object pipeline")
    config = deepcopy(DEFAULTS)
    config.update(value)
    for key, default in DEFAULTS.items():
        item = config[key]
        if isinstance(default, bool):
            valid = type(item) is bool
        elif isinstance(default, int):
            valid = type(item) is int and item > 0
        elif isinstance(default, float):
            valid = type(item) in (int, float) and 0 <= item <= 1
        elif isinstance(default, list):
            valid = isinstance(item, list) and all(isinstance(s, str) and s.strip() for s in item)
        else:
            valid = isinstance(item, str) and (bool(item.strip()) or key == "model")
        if not valid:
            raise ValueError(f"Invalid pipeline.{key}")
    if config["abstract_mode"] != "original":
        raise ValueError("abstract_mode currently supports original only (metadata verbatim)")
    if config["rule_weight"] + config["llm_weight"] <= 0:
        raise ValueError("Scoring weights must have a positive sum")
    if config["llm_shortlist"] < config["weekly_new"]:
        raise ValueError("llm_shortlist must be >= weekly_new")
    for key in ("post_dir", "queue_path", "draft_dir", "archive_dir", "log_dir"):
        path = Path(config[key])
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError(f"pipeline.{key} must be a repository-relative path")
    if Path(config["post_dir"]).parts[0] != "content":
        raise ValueError("post_dir must be inside content/")
    if Path(config["draft_dir"]).parts[0] == "content":
        raise ValueError("draft_dir must be outside content/")
    return config
