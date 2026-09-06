"""Dependency boundary for the REST adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from ._adapter_import_boundary import SRC_ROOT, is_module_or_child, scan_path, scan_source

SERVER_DIR = SRC_ROOT / "server"
PRIVATE_ALLOWANCES = {
    "notebooklm._adapter_support": {
        "server/__main__.py",
        "server/_auth.py",
        "server/_errors.py",
        "server/_limits.py",
        "server/app.py",
        "server/routes/meta.py",
    },
    "notebooklm._source.batch": {"server/routes/sources.py"},
    "notebooklm._loop_affinity": {"server/_limits.py"},
    "notebooklm._version_info": {"server/routes/meta.py"},
}


def _server_files() -> list[Path]:
    return sorted(SERVER_DIR.rglob("*.py"))


def _violations(path: Path) -> list[str]:
    relative = path.relative_to(SRC_ROOT).as_posix()
    bad: list[str] = []
    for imported in scan_path(path):
        target = imported.target
        forbidden = any(is_module_or_child(target, prefix) for prefix in ("click", "rich", "cli"))
        forbidden |= is_module_or_child(target, "notebooklm.cli")
        forbidden |= is_module_or_child(target, "notebooklm.mcp")
        if forbidden:
            bad.append(f"line {imported.line}: {target}")
            continue
        if target.startswith("notebooklm._") and not is_module_or_child(target, "notebooklm._app"):
            allowed = next(
                (modules for prefix, modules in PRIVATE_ALLOWANCES.items() if is_module_or_child(target, prefix)),
                set(),
            )
            if relative not in allowed:
                bad.append(f"line {imported.line}: {target}")
    return bad


def test_server_dir_exists() -> None:
    assert SERVER_DIR.is_dir(), f"expected server package at {SERVER_DIR}"


@pytest.mark.parametrize("path", _server_files(), ids=lambda p: str(p.relative_to(SRC_ROOT.parent.parent)))
def test_server_imports_follow_adapter_boundary(path: Path) -> None:
    bad = _violations(path)
    assert not bad, f"{path.relative_to(SRC_ROOT)} imports forbidden dependencies: {bad}"


@pytest.mark.parametrize(
    "source",
    (
        "from ...mcp import server\n",
        "from ... import mcp\n",
        "if TYPE_CHECKING:\n    from ..._web import transport\n",
        "__import__('notebooklm.cli.context')\n",
    ),
)
def test_server_scanner_resolves_relative_type_only_and_literal_dynamic_edges(source: str) -> None:
    targets = {item.target for item in scan_source(source, package="notebooklm.server.routes")}
    assert any(
        target.startswith(("notebooklm._", "notebooklm.mcp", "notebooklm.cli"))
        for target in targets
    )
