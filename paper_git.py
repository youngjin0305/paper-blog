"""Scoped Git publishing with a durable outbox for commit/push recovery."""
import json
from pathlib import Path
import subprocess

from garden import atomic_write


class Publisher:
    def __init__(self, root, config, log):
        self.root = Path(root)
        self.config = config
        self.log = log
        self.outbox = self.root / "data/paper-publish-pending.json"

    def git(self, *args, check=True):
        result = subprocess.run(["git", *args], cwd=self.root, capture_output=True,
                                encoding="utf-8", errors="replace", timeout=self.config["timeout"], shell=False)
        if check and result.returncode:
            # Do not log raw stderr (remote URLs can contain credentials).
            raise RuntimeError(f"git {args[0]} failed (exit {result.returncode})")
        return result

    def preflight(self):
        self.git("rev-parse", "--show-toplevel")
        if self.git("diff", "--cached", "--name-only").stdout.strip():
            raise RuntimeError("Git index already has staged changes; leave them untouched")

    def prepare(self, post_path, queue_path, document, queue):
        self.preflight()
        if (self.root / post_path).exists():
            raise RuntimeError("Post already exists; refusing to overwrite it")
        payload = {"postPath": post_path, "queuePath": queue_path, "document": document,
                   "queue": queue, "headBefore": self.git("rev-parse", "HEAD").stdout.strip(),
                   "queueBefore": (self.root / queue_path).read_text(encoding="utf-8") if (self.root / queue_path).exists() else None,
                   "message": "post: [논문 요약] " + json.loads(document[4:].split("\n---\n", 1)[0])["title"][:72],
                   "phase": "prepared"}
        atomic_write(self.outbox, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    def resume(self):
        if not self.outbox.exists():
            return False
        payload = json.loads(self.outbox.read_text(encoding="utf-8"))
        paths = [payload["postPath"], payload["queuePath"]]
        for path in paths:
            if not (self.root / path).resolve().is_relative_to(self.root.resolve()):
                raise ValueError("Invalid publish outbox path")
        try:
            if payload["phase"] == "prepared":
                # If a crash happened after commit, find the exact transaction in local history.
                commits = self.git("rev-list", payload["headBefore"] + "..HEAD").stdout.splitlines()
                committed = False
                expected_queue = json.dumps(payload["queue"], ensure_ascii=False, indent=2) + "\n"
                for commit in commits:
                    names = set(self.git("diff-tree", "--no-commit-id", "--name-only", "-r", commit).stdout.splitlines())
                    if names == set(paths) and self.git("show", f"{commit}:{paths[0]}").stdout == payload["document"] and self.git("show", f"{commit}:{paths[1]}").stdout == expected_queue:
                        committed = True
                        break
                if not committed:
                    staged = set(self.git("diff", "--cached", "--name-only").stdout.splitlines())
                    if staged - set(paths):
                        raise RuntimeError("Unrelated staged files; publish is pending")
                    for path, content in zip(paths, (payload["document"], expected_queue)):
                        target = self.root / path
                        if path == paths[0] and target.exists() and target.read_text(encoding="utf-8") != content:
                            raise RuntimeError("Pending post was edited; refusing to overwrite it")
                        if path == paths[1] and target.exists() and target.read_text(encoding="utf-8") not in (content, payload.get("queueBefore")):
                            raise RuntimeError("Pending queue was edited; refusing to overwrite it")
                        atomic_write(target, content)
                    self.git("add", "--", *paths)
                    self.git("commit", "-m", payload["message"], "--", *paths)
                payload["phase"] = "committed"
                atomic_write(self.outbox, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            self.git("push")
            self.outbox.unlink()
            self.log("Published pending post with normal git push")
            return True
        except (RuntimeError, subprocess.TimeoutExpired):
            self.log("Git publish pending; next non-dry run will retry before changing the queue")
            raise
