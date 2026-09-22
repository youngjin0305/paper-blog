"""Pure queue operations; callers hold the process lock while persisting."""
from copy import deepcopy
from datetime import datetime
import re

from garden import now


def canonical_id(identifier, source):
    if source == "arxiv":
        return "arxiv:" + re.sub(r"v\d+$", "", identifier.removeprefix("arxiv:"))
    return identifier if identifier.startswith(source + ":") else source + ":" + identifier


def empty_queue():
    return {"version": 1, "papers": [], "seen": [], "lastWeeklyAt": None}


def entry(paper, status="candidate", timestamp=None):
    result = deepcopy(paper)
    result["id"] = canonical_id(paper["id"], paper["source"])
    result.update(addedAt=timestamp or now(), status=status, score=0, scoreDetail={},
                  rationale="", weeksInQueue=0, lastRankedAt=None, failCount=0, postPath=None)
    return result


def ordered(queue):
    pins = sorted((p for p in queue["papers"] if p["status"] == "pinned"), key=lambda p: p["addedAt"])
    candidates = sorted((p for p in queue["papers"] if p["status"] == "candidate"),
                        key=lambda p: (-p["score"], p["addedAt"], p["id"]))
    return pins + candidates


def weekly_completed(queue, timestamp):
    last = queue.get("lastWeeklyAt")
    if not last:
        return False
    # Use the scheduler's local calendar week so a Tuesday setup does not skip next Monday.
    week = lambda stamp: datetime.fromisoformat(stamp).astimezone().isocalendar()[:2]
    return week(last) == week(timestamp)


def pin(queue, paper, note=""):
    identifier = canonical_id(paper["id"], paper["source"])
    existing = next((p for p in queue["papers"] if p["id"] == identifier), None)
    if existing is None:
        existing = entry(paper, "pinned")
        queue["papers"].append(existing)
    # Keep addedAt for the requested FIFO order, even when promoting an old entry.
    existing["status"] = "pinned"
    existing["note"] = note
    if identifier not in queue["seen"]:
        queue["seen"].append(identifier)
    return existing


def merge_weekly(queue, newcomers, config, timestamp):
    # A scheduler restart in the same week must not age or expire the pool twice.
    if weekly_completed(queue, timestamp):
        return False
    seen = set(queue["seen"]) | {p["id"] for p in queue["papers"]}
    for paper in sorted(newcomers, key=lambda p: -p["score"]):
        if paper["id"] not in seen:
            queue["papers"].append(paper)
            seen.add(paper["id"])
    for paper in queue["papers"]:
        if paper["status"] == "candidate" and paper["weeksInQueue"] >= config["expiry_weeks"]:
            paper["status"] = "expired"
    candidates = [p for p in ordered(queue) if p["status"] == "candidate"]
    for paper in candidates[config["pool_limit"]:]:
        paper["status"] = "expired"
    for paper in candidates[:config["pool_limit"]]:
        paper["weeksInQueue"] += 1
        paper["lastRankedAt"] = timestamp
    queue["seen"] = sorted(seen)
    queue["lastWeeklyAt"] = timestamp
    return True
