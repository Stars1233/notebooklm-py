"""Package-aware import scanner shared by the three adapter boundary guards.

The adapter boundary is an authored-code rule. Imports under ``TYPE_CHECKING``
and literal dynamic imports still express a dependency, so this scanner records
them alongside ordinary absolute and relative imports.
"""

from __future__ import annotations

import ast
import importlib.util
from dataclasses import dataclass
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "notebooklm"


@dataclass(frozen=True)
class AdapterImport:
    target: str
    line: int
    type_only: bool


def module_identity(path: Path) -> tuple[str, str]:
    """Return the module name and package used for relative-import resolution."""
    parts = list(path.relative_to(SRC_ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
        module = ".".join(("notebooklm", *parts))
        return module, module
    module = ".".join(("notebooklm", *parts))
    return module, module.rpartition(".")[0]


def _is_type_checking_guard(node: ast.AST) -> bool:
    return (isinstance(node, ast.Name) and node.id == "TYPE_CHECKING") or (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "typing"
        and node.attr == "TYPE_CHECKING"
    )


class _Visitor(ast.NodeVisitor):
    def __init__(self, package: str) -> None:
        self._package = package
        self._type_only = False
        self.imports: list[AdapterImport] = []

    def visit_If(self, node: ast.If) -> None:
        if not _is_type_checking_guard(node.test):
            self.generic_visit(node)
            return
        old_type_only = self._type_only
        self._type_only = True
        for child in node.body:
            self.visit(child)
        self._type_only = old_type_only
        for child in node.orelse:
            self.visit(child)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._record(alias.name, node.lineno)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if node.level:
            module = importlib.util.resolve_name(f"{'.' * node.level}{module}", self._package)
        self._record(module, node.lineno)
        for alias in node.names:
            self._record(f"{module}.{alias.name}", node.lineno)

    def visit_Call(self, node: ast.Call) -> None:
        function = node.func.id if isinstance(node.func, ast.Name) else (
            node.func.attr if isinstance(node.func, ast.Attribute) else None
        )
        if (
            function in {"__import__", "import_module"}
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            self._record(node.args[0].value, node.lineno)
        self.generic_visit(node)

    def _record(self, target: str, line: int) -> None:
        self.imports.append(AdapterImport(target=target, line=line, type_only=self._type_only))


def scan_source(source: str, *, package: str) -> list[AdapterImport]:
    """Resolve every import authored by ``source`` in ``package``."""
    visitor = _Visitor(package)
    visitor.visit(ast.parse(source))
    return visitor.imports


def scan_path(path: Path) -> list[AdapterImport]:
    """Resolve every import authored by ``path``."""
    _, package = module_identity(path)
    return scan_source(path.read_text(encoding="utf-8"), package=package)


def is_module_or_child(target: str, parent: str) -> bool:
    return target == parent or target.startswith(f"{parent}.")
