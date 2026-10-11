"""Dependency rule of ADR-011: `core` never imports `f1`, so the next themes can copy `core` as is."""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
FORBIDDEN = "f1"


def forbidden_imports(source: str, forbidden: str = FORBIDDEN) -> list[str]:
    """Names of the modules under `forbidden` that this source imports, at any depth of the file."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        found += [name for name in names if name == forbidden or name.startswith(f"{forbidden}.")]
    return found


@pytest.mark.parametrize("path", sorted((SRC / "core").rglob("*.py")), ids=lambda p: str(p.relative_to(SRC)))
def test_core_does_not_import_the_theme(path: Path) -> None:
    assert forbidden_imports(path.read_text()) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import f1", ["f1"]),
        ("import f1.api as api", ["f1.api"]),
        ("from f1 import api", ["f1"]),
        ("from f1.api import app", ["f1.api"]),
        ("def f():\n    from f1.api import app", ["f1.api"]),
        ("import f1x\nfrom core import gateway", []),
        ("from . import gateway", []),
    ],
)
def test_the_check_catches_every_import_form(source: str, expected: list[str]) -> None:
    assert forbidden_imports(source) == expected
