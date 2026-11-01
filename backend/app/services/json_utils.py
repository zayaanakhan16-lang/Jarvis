"""Tolerant JSON extraction from model output.

Models sometimes wrap JSON in prose or code fences. Rather than failing, we
recover the object and report when recovery was needed.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
# Trailing commas before a closing brace or bracket.
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")
# A single-quoted string value, e.g. 'text' rather than "text".
_SINGLE_QUOTED = re.compile(r"(?<![\\\w])'([^'\n]*)'")


def _repair(candidate: str) -> str:
    """Apply the small repairs models most often need.

    Only structural noise is fixed here; the result is still parsed by
    ``json.loads``, so a repair that produces invalid JSON is simply rejected.
    """
    repaired = _TRAILING_COMMA.sub(r"\1", candidate)
    if '"' not in repaired and "'" in repaired:
        repaired = _SINGLE_QUOTED.sub(lambda m: json.dumps(m.group(1)), repaired)
    return repaired


def extract_json(text: str) -> tuple[Any | None, str | None]:
    """Return ``(parsed, error)``. ``parsed`` is None when nothing could be read."""
    if not text or not text.strip():
        return None, "Model returned an empty response."

    candidates: list[str] = []
    stripped = text.strip()
    candidates.append(stripped)
    candidates.extend(match.strip() for match in _FENCE.findall(text))

    # Fall back to the outermost brace pair.
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        candidates.append(text[first : last + 1])

    for candidate in candidates:
        if not candidate:
            continue
        for attempt in (candidate, _repair(candidate)):
            try:
                return json.loads(attempt), None
            except json.JSONDecodeError:
                continue
    return None, "Could not parse JSON from the model response."


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def clamp_int(value: Any, *, low: int, high: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))
