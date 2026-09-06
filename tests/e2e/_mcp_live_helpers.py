"""Shared helpers for the live MCP e2e suites.

A ``_``-prefixed (non-``test_``) module so the per-suite modules
(``test_mcp.py``, ``test_mcp_http.py``, ``test_mcp_contracts.py``) can share the
in-memory FastMCP driver + the downloadable-artifact mapping WITHOUT importing
one ``test_*`` module from another (forbidden by
``tests/_guardrails/test_no_cross_test_imports.py``).

Imported only by modules that have already ``pytest.importorskip("fastmcp")``,
so the ``fastmcp`` import here is safe (it never loads on a no-``mcp`` install).
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Mapping
from typing import Any

import pytest
from fastmcp import Client

from notebooklm import NotebookLMClient
from notebooklm.mcp.server import create_server

from ._artifact_helpers import studio_item_may_have_download_payload
from ._generation_helpers import _TYPED_RATE_LIMIT_ATTR

#: Merged ``studio_list`` item ``type`` values (hyphenated, the shared Studio
#: vocabulary) whose download is wired through ``studio_download``. An item's
#: ``type`` doubles as the ``studio_download`` ``artifact_type`` key, so no
#: translation is needed (unlike the old underscored ``_artifact_type`` codes).
DOWNLOADABLE_ARTIFACT_TYPES = {
    "audio",
    "video",
    "slide-deck",
    "infographic",
    "report",
    "mind-map",
    "data-table",
    "quiz",
    "flashcards",
}

_ANDROID_INVENTORY_ONLY_SLIDE_DETAIL = "PDF URL not available in artifact data"


def structured_failure_detail(result: object) -> str | None:
    """Return the typed MCP failure detail without accepting legacy flat errors."""

    if not isinstance(result, Mapping):
        return None
    failure = result.get("failure")
    if not isinstance(failure, Mapping):
        return None
    detail = failure.get("detail")
    return detail if isinstance(detail, str) else None


def is_android_inventory_only_slide_failure(
    result: object,
    *,
    backend: str,
    artifact_type: str,
) -> bool:
    """Recognize only the typed failure for an Android slide without a PDF URL."""

    detail = structured_failure_detail(result)
    failure = result.get("failure") if isinstance(result, Mapping) else None
    return (
        isinstance(result, Mapping)
        and isinstance(failure, Mapping)
        and backend == "android"
        and artifact_type == "slide-deck"
        and result.get("outcome") == "error"
        and failure.get("reason") == "download_failed"
        and detail is not None
        and _ANDROID_INVENTORY_ONLY_SLIDE_DETAIL in detail
    )


def _only_typed_rate_limit_skip(error: BaseException) -> BaseException | None:
    """Unwrap FastMCP task groups only when every leaf is our quota skip."""

    pending = [error]
    leaves: list[BaseException] = []
    while pending:
        current = pending.pop()
        children = getattr(current, "exceptions", None)
        if isinstance(children, tuple) and children:
            pending.extend(children)
        else:
            leaves.append(current)
    if leaves and all(
        isinstance(leaf, pytest.skip.Exception)
        and getattr(leaf, _TYPED_RATE_LIMIT_ATTR, False) is True
        for leaf in leaves
    ):
        return leaves[0]
    return None


def pick_downloadable_artifact(
    items: list[dict[str, Any]], *, backend: str
) -> dict[str, Any] | None:
    """Return the first ready, downloadable artifact among merged studio ``items``.

    Operates on the unified ``studio_list`` item shape: a hyphenated ``type``
    discriminator (``note`` items and non-downloadable types are skipped) plus a
    tolerant ``status_label`` check ("ready" tolerates a missing/None label as well
    as the terminal ``ready``/``completed`` states). Lets a test reuse whatever
    artifact a notebook already has and skip cleanly when none qualifies.
    """
    candidates = [
        item
        for item in items
        if item.get("type") in DOWNLOADABLE_ARTIFACT_TYPES
        and item.get("status_label") in (None, "ready", "completed")
        and studio_item_may_have_download_payload(item, backend=backend)
    ]
    confirmed = next(
        (
            item
            for item in candidates
            if not (
                backend == "android" and item.get("type") == "slide-deck" and not item.get("url")
            )
        ),
        None,
    )
    return confirmed or (candidates[0] if candidates else None)


@contextlib.asynccontextmanager
async def mcp_client(real_client: NotebookLMClient) -> AsyncIterator[Client]:
    """Yield an in-memory FastMCP ``Client`` bound to ``real_client``.

    Wraps the already-open E2E ``client`` fixture in a no-op async-context-manager
    factory so the server lifespan re-yields the same client (the fixture owns the
    open/close lifecycle; the factory must NOT close it).
    """

    @contextlib.asynccontextmanager
    async def factory() -> AsyncIterator[NotebookLMClient]:
        yield real_client

    server = create_server(client_factory=factory)
    async with Client(server) as client:
        yield client


async def call_tool(
    real_client: NotebookLMClient, name: str, args: dict[str, Any] | None = None
) -> Any:
    """Call one MCP tool over the in-memory transport and return its structured content."""
    try:
        async with mcp_client(real_client) as client:
            result = await client.call_tool(name, args or {})
    except BaseException as error:
        # pytest's skip signal intentionally derives from BaseException. FastMCP's
        # in-memory task groups preserve it, but nest it in BaseExceptionGroup
        # layers while unwinding. Recover only our machine-marked quota signal;
        # mixed groups and every unrelated base exception still fail loudly.
        rate_limit_skip = _only_typed_rate_limit_skip(error)
        if rate_limit_skip is None:
            raise
        raise rate_limit_skip from None
    # Every tool in this suite returns a structured dict on success. Assert it here
    # so a caller subscripting the result fails LOUDLY (with the tool name) instead
    # of with an opaque ``NoneType`` subscript error — and so the assertion can't
    # be silently masked into a passing test by a ``(x or {})`` fallback.
    assert result.structured_content is not None, (
        f"MCP tool {name!r} returned no structured content"
    )
    return result.structured_content
