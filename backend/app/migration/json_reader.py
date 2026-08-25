from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SourceJsonError(ValueError):
    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key {key!r}")
        result[key] = value
    return result


def _remove_trailing_commas(text: str) -> str:
    """Remove commas before ]/} only when they occur outside JSON strings."""

    output: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        character = text[index]
        if in_string:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            output.append(character)
            index += 1
            continue
        if character == ",":
            lookahead = index + 1
            while lookahead < len(text) and text[lookahead].isspace():
                lookahead += 1
            if lookahead < len(text) and text[lookahead] in "]}":
                index += 1
                continue
        output.append(character)
        index += 1
    return "".join(output)


def read_json(path: Path, *, allow_trailing_commas: bool = False) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
        if allow_trailing_commas:
            text = _remove_trailing_commas(text)
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise SourceJsonError(path, str(exc)) from exc
