"""Dependency boundary for the MCP adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from ._adapter_import_boundary import SRC_ROOT, is_module_or_child, scan_path, scan_source

MCP_DIR = SRC_ROOT / "mcp"

# Adapter-owned hosting/deprecation seams, deliberately exact. Domain code
# crosses through ``_app`` or public modules; only source-batch settlement may
# attach private journal evidence until that primitive has a public equivalent.
PRIVATE_ALLOWANCES = {
    "notebooklm._adapter_support": {
        "mcp/__main__.py",
        "mcp/_chattasks.py",
        "mcp/_clientprovider.py",
        "mcp/_errors.py",
        "mcp/_host_guard.py",
        "mcp/server.py",
    },
    "notebooklm._deprecation": {"mcp/_confirm.py", "mcp/tools/research.py"},
    "notebooklm._source.batch": {"mcp/tools/sources.py"},
    "notebooklm._version_info": {"mcp/tools/meta.py"},
}


def _mcp_files() -> list[Path]:
    return sorted(MCP_DIR.rglob("*.py"))


def _violations(path: Path) -> list[str]:
    relative = path.relative_to(SRC_ROOT).as_posix()
    bad: list[str] = []
    for imported in scan_path(path):
        target = imported.target
        forbidden = any(is_module_or_child(target, prefix) for prefix in ("click", "rich", "cli"))
        forbidden |= is_module_or_child(target, "notebooklm.cli")
        forbidden |= is_module_or_child(target, "notebooklm.server")
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


def test_mcp_dir_exists() -> None:
    assert MCP_DIR.is_dir(), f"expected MCP package at {MCP_DIR}"


@pytest.mark.parametrize("path", _mcp_files(), ids=lambda p: str(p.relative_to(SRC_ROOT.parent.parent)))
def test_mcp_imports_follow_adapter_boundary(path: Path) -> None:
    bad = _violations(path)
    assert not bad, f"{path.relative_to(SRC_ROOT)} imports forbidden dependencies: {bad}"


@pytest.mark.parametrize(
    "source",
    (
        "from ...server import app\n",
        "from ... import server\n",
        "if TYPE_CHECKING:\n    from ..._web import transport\n",
        "import importlib\nimportlib.import_module('notebooklm.cli.context')\n",
    ),
)
def test_mcp_scanner_resolves_relative_type_only_and_literal_dynamic_edges(source: str) -> None:
    targets = {item.target for item in scan_source(source, package="notebooklm.mcp.tools")}
    assert any(
        target.startswith(("notebooklm._", "notebooklm.server", "notebooklm.cli"))
        for target in targets
    )
