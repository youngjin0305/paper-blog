"""Model-only routing shared by the web app and scheduled pipeline."""
import re

DEFAULT_MODEL = "gemini-3.8-flash-high"


def resolve_model(value):
    if not isinstance(value, str):
        raise ValueError("모델 설정은 문자열이어야 합니다.")
    value = value.strip() or DEFAULT_MODEL
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._/-]{0,119}", value):
        raise ValueError("모델 이름 또는 gemini/모델, codex/모델, claude/모델 형식을 사용하세요.")
    if "/" in value:
        provider, model = value.split("/", 1)
        if provider not in ("gemini", "codex", "claude") or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", model):
            raise ValueError("지원하는 모델 공급자는 gemini, codex, claude입니다.")
        return provider, model
    if value in ("gemini", "codex", "claude"):
        return value, ""
    if value.startswith("claude-") or value in ("sonnet", "opus", "haiku"):
        return "claude", value
    if value.startswith(("gpt-", "codex-")) or re.match(r"^o\d(?:-|$)", value):
        return "codex", value
    # Preserve existing Gemini/Antigravity model IDs and CLI aliases.
    return "gemini", value
