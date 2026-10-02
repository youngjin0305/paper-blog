"""Find TeX math without treating code blocks or inline code as equations."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
import shutil
import subprocess


@dataclass(frozen=True)
class MathSpan:
    start: int
    end: int
    latex: str
    display: bool


def math_spans(text):
    """Return complete $/$$/\\(\\)/\\[\\] spans and delimiter errors."""
    spans, errors = [], []
    i = 0
    fence = None

    def escaped(position):
        backslashes = 0
        while position > backslashes and text[position - backslashes - 1] == "\\":
            backslashes += 1
        return backslashes % 2 == 1

    while i < len(text):
        if i == 0 or text[i - 1] == "\n":
            marker = re.match(r" {0,3}(`{3,}|~{3,})", text[i:])
            if marker:
                run = marker[1]
                if fence is None:
                    fence = run
                elif run[0] == fence[0] and len(run) >= len(fence):
                    fence = None
                newline = text.find("\n", i)
                i = len(text) if newline < 0 else newline + 1
                continue
        if fence:
            newline = text.find("\n", i)
            i = len(text) if newline < 0 else newline + 1
            continue
        if text[i] == "`" and not escaped(i):
            run = len(text[i:]) - len(text[i:].lstrip("`"))
            closing = text.find("`" * run, i + run)
            if closing >= 0:
                i = closing + run
                continue
        opening = None
        if not escaped(i):
            if text.startswith("$$", i):
                opening = ("$$", "$$", True)
            elif text.startswith("\\[", i):
                opening = ("\\[", "\\]", True)
            elif text.startswith("\\(", i):
                opening = ("\\(", "\\)", False)
            elif text[i] == "$":
                opening = ("$", "$", False)
        if opening is None:
            i += 1
            continue
        left, right, display = opening
        j = i + len(left)
        while j < len(text):
            if text.startswith(right, j) and not escaped(j):
                if right != "$" or (not text.startswith("$$", j) and text[j - 1] != "$"):
                    break
            j += 1
        if j == len(text):
            errors.append(f"Unclosed math delimiter {left} at line {text.count(chr(10), 0, i) + 1}")
            i += len(left)
            continue
        latex = text[i + len(left):j]
        if not latex.strip():
            errors.append(f"Empty math at line {text.count(chr(10), 0, i) + 1}")
        else:
            spans.append(MathSpan(i, j + len(right), latex, display))
        i = j + len(right)
    return spans, errors


def validate_math(text):
    """Check generated TeX with the same KaTeX version used by the site."""
    spans, errors = math_spans(text)
    if not spans:
        return errors
    node = shutil.which("node")
    if not node:
        return errors + ["Node.js is required to validate TeX math before publishing"]
    script = Path(__file__).resolve().parent / "scripts" / "validate_math.cjs"
    payload = [{"latex": span.latex, "display": span.display} for span in spans]
    try:
        result = subprocess.run([node, str(script)], input=json.dumps(payload), capture_output=True,
                                encoding="utf-8", errors="replace", timeout=20, check=True)
        failures = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return errors + ["KaTeX math validation unavailable; refusing to publish unverified equations"]
    for failure in failures:
        span = spans[failure["index"]]
        line = text.count("\n", 0, span.start) + 1
        errors.append(f"Invalid TeX at line {line}: {failure['message'][:180]}")
    return errors
