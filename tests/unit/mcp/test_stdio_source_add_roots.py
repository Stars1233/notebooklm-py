"""MCP stdio ``source_add(source_type="file", path=...)`` allowed-root boundary.

Host-path file-add is default-deny until ``NOTEBOOKLM_MCP_ALLOWED_ROOTS`` is set.
These tests drive the real ``source_add`` tool (not a reimplementation) from the
preflight: a denied path must fail VALIDATION before ``add_file``.
"""

from __future__ import annotations

import base64
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastmcp")

from fastmcp import Client  # noqa: E402 - after importorskip guard
from fastmcp.exceptions import ToolError  # noqa: E402 - after importorskip guard

from notebooklm._types.sources import SourceType  # noqa: E402 - after importorskip guard
from notebooklm.exceptions import AuthError  # noqa: E402 - after importorskip guard
from notebooklm.mcp.server import create_server  # noqa: E402 - after importorskip guard
from notebooklm.mcp.tools._fileupload import (  # noqa: E402 - after importorskip guard
    ALLOWED_ROOTS_ENV,
)
from notebooklm.rpc.types import DriveSourceStatus, SourceStatus  # noqa: E402 - after importorskip

from .conftest import AsyncMock  # noqa: E402 - after importorskip guard

NB_ID = "11111111-1111-1111-1111-111111111111"


@dataclass
class _ReadyPdf:
    id: str
    title: str | None = None

    @property
    def is_ready(self) -> bool:
        return True

    @property
    def is_error(self) -> bool:
        return False

    @property
    def kind(self) -> SourceType:
        return SourceType.PDF

    @property
    def status(self) -> SourceStatus:
        return SourceStatus.READY

    @property
    def drive_status(self) -> DriveSourceStatus | None:
        return None

    @property
    def is_drive_degraded(self) -> bool:
        return False


def _pdf(directory: Path, name: str = "doc.pdf") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("x")
    return path


async def test_stdio_file_add_without_roots_is_denied(
    mcp_call, mock_client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ALLOWED_ROOTS_ENV, raising=False)
    doc = _pdf(tmp_path)
    mock_client.sources.add_file = AsyncMock()
    with pytest.raises(ToolError) as excinfo:
        await mcp_call(
            "source_add",
            {"notebook": NB_ID, "source_type": "file", "path": str(doc)},
        )
    message = str(excinfo.value)
    assert message.startswith("VALIDATION:"), message
    assert ALLOWED_ROOTS_ENV in message
    mock_client.sources.add_file.assert_not_called()


async def test_stdio_file_add_default_deny_precedes_lazy_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ALLOWED_ROOTS_ENV, raising=False)
    doc = _pdf(tmp_path)

    @contextlib.asynccontextmanager
    async def failing_factory() -> AsyncIterator[MagicMock]:
        raise AuthError("expired credentials that must not mask validation")
        yield  # pragma: no cover - unreachable, keeps this an async generator

    async with Client(create_server(client_factory=failing_factory)) as client:
        with pytest.raises(ToolError) as excinfo:
            await client.call_tool(
                "source_add",
                {"notebook": NB_ID, "source_type": "file", "path": str(doc)},
            )
    message = str(excinfo.value)
    assert message.startswith("VALIDATION:"), message
    assert ALLOWED_ROOTS_ENV in message
    assert "expired credentials" not in message


async def test_stdio_file_add_inside_allowed_root(
    mcp_call, mock_client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "uploads"
    doc = _pdf(root)
    monkeypatch.setenv(ALLOWED_ROOTS_ENV, str(root))
    mock_client.sources.add_file = AsyncMock(return_value=_ReadyPdf(id="src-1", title="doc.pdf"))
    result = await mcp_call(
        "source_add",
        {"notebook": NB_ID, "source_type": "file", "path": str(doc)},
    )
    assert result.structured_content["source"]["id"] == "src-1"
    mock_client.sources.add_file.assert_awaited_once()
    uploaded = Path(mock_client.sources.add_file.await_args.args[1])
    assert uploaded == doc.resolve()


async def test_stdio_file_add_outside_allowed_root_rejects_regular_pdf(
    mcp_call, mock_client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setenv(ALLOWED_ROOTS_ENV, str(root))
    outside = _pdf(tmp_path / "other")
    mock_client.sources.add_file = AsyncMock()
    with pytest.raises(ToolError) as excinfo:
        await mcp_call(
            "source_add",
            {"notebook": NB_ID, "source_type": "file", "path": str(outside)},
        )
    message = str(excinfo.value)
    assert message.startswith("VALIDATION:"), message
    assert ALLOWED_ROOTS_ENV in message
    mock_client.sources.add_file.assert_not_called()


async def test_stdio_file_add_rejects_storage_state_inside_allowed_root(
    mcp_call, mock_client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "uploads"
    cred = _pdf(root, "storage_state.json")
    monkeypatch.setenv(ALLOWED_ROOTS_ENV, str(root))
    mock_client.sources.add_file = AsyncMock()
    with pytest.raises(ToolError) as excinfo:
        await mcp_call(
            "source_add",
            {"notebook": NB_ID, "source_type": "file", "path": str(cred)},
        )
    message = str(excinfo.value)
    assert message.startswith("VALIDATION:"), message
    assert "credential" in message.lower()
    mock_client.sources.add_file.assert_not_called()


async def test_stdio_file_add_rejects_symlink(
    mcp_call, mock_client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "uploads"
    target = _pdf(root, "real.pdf")
    link = root / "link.pdf"
    link.symlink_to(target)
    monkeypatch.setenv(ALLOWED_ROOTS_ENV, str(root))
    mock_client.sources.add_file = AsyncMock()
    with pytest.raises(ToolError) as excinfo:
        await mcp_call(
            "source_add",
            {"notebook": NB_ID, "source_type": "file", "path": str(link)},
        )
    message = str(excinfo.value)
    assert message.startswith("VALIDATION:"), message
    assert "symlink" in message.lower()
    mock_client.sources.add_file.assert_not_called()


async def test_bytes_base64_still_works_without_allowed_roots(
    mcp_call, mock_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ALLOWED_ROOTS_ENV, raising=False)
    mock_client.sources.add_file = AsyncMock(
        return_value=_ReadyPdf(id="src-b64", title="report.pdf")
    )
    result = await mcp_call(
        "source_add",
        {
            "notebook": NB_ID,
            "source_type": "file",
            "bytes_base64": base64.b64encode(b"%PDF-1.4 hi").decode(),
            "filename": "report.pdf",
        },
    )
    assert result.structured_content["source"]["id"] == "src-b64"
    mock_client.sources.add_file.assert_awaited_once()
