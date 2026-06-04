"""Boundary lint: pydantic is confined to boundary.py (AST-walked).

Keeps the polars/attrs hot path free of pydantic per the boundary contract. If a
future edit imports pydantic into clock.py, records.py, or a source module, this
fails at PR time rather than letting per-instance validation creep into the inner
loop.
"""

from __future__ import annotations

import ast
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parents[2] / "src" / "riskpremia" / "data"


def _imports_pydantic(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "pydantic" or alias.name.startswith("pydantic."):
                    return True
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "pydantic" or module.startswith("pydantic."):
                return True
    return False


def _data_modules() -> list[Path]:
    return sorted(p for p in _DATA_DIR.rglob("*.py"))


def test_only_boundary_imports_pydantic() -> None:
    offenders = []
    for path in _data_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if _imports_pydantic(tree) and path.name != "boundary.py":
            offenders.append(path.relative_to(_DATA_DIR).as_posix())
    assert offenders == [], f"pydantic imported outside boundary.py: {offenders}"


def test_boundary_actually_imports_pydantic() -> None:
    boundary = _DATA_DIR / "boundary.py"
    tree = ast.parse(boundary.read_text(encoding="utf-8"))
    assert _imports_pydantic(tree), "boundary.py is the IO boundary and must import pydantic"
