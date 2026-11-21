"""Translations use exactly the placeholders of strings.json (HA rejects any others)."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import pytest

BASE = Path(__file__).parents[1] / "custom_components" / "vector"
PLACEHOLDER = re.compile(r"\{([^{}]+)\}")


def _flatten(node: Any, prefix: str = "") -> dict[str, str]:
    if isinstance(node, dict):
        out: dict[str, str] = {}
        for key, value in node.items():
            out.update(_flatten(value, f"{prefix}.{key}" if prefix else key))
        return out
    return {prefix: node} if isinstance(node, str) else {}


@pytest.mark.parametrize("lang", sorted(p.stem for p in (BASE / "translations").glob("*.json")))
def test_placeholders_match_strings_json(lang: str) -> None:
    source = _flatten(json.loads((BASE / "strings.json").read_text()))
    translated = _flatten(json.loads((BASE / "translations" / f"{lang}.json").read_text()))
    wrong = {
        key: (set(PLACEHOLDER.findall(text)), set(PLACEHOLDER.findall(source[key])))
        for key, text in translated.items()
        if key in source and set(PLACEHOLDER.findall(text)) != set(PLACEHOLDER.findall(source[key]))
    }
    assert wrong == {}
