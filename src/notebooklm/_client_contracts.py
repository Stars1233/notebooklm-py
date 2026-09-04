"""Import-light contracts shared by the public client and Web lifecycle."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Protocol

import httpx

from ._auth.storage import CookieSaveResult, CookieSnapshot


class SaveCookiesToStorage(Protocol):
    """Callable shape for the exact v0.x cookie-save callback invocation."""

    def __call__(
        self,
        cookie_jar: httpx.Cookies,
        path: Path,
        /,
        *,
        original_snapshot: CookieSnapshot | None,
        return_result: bool,
    ) -> bool | CookieSaveResult: ...


CookieSaver = SaveCookiesToStorage
CookieRotator = Callable[..., Awaitable[None]]

BackendName = Literal["web", "android"]

_NAMESPACE_NAMES = (
    "notebooks",
    "sources",
    "artifacts",
    "chat",
    "research",
    "notes",
    "mind_maps",
    "settings",
    "sharing",
    "labels",
    "collections",
)


def installed_backend_map(backend: BackendName) -> Mapping[str, BackendName]:
    """Return an immutable, explicit namespace-to-backend report."""

    return MappingProxyType(dict.fromkeys(_NAMESPACE_NAMES, backend))


@dataclass(frozen=True)
class BackendAssembly:
    """Import-light result returned by either concrete backend assembler."""

    backend: BackendName
    runtime: Any
    collaborators: Any
    transports: tuple[Any, ...]
    loop_participants: tuple[Any, ...]
    backends: Mapping[str, BackendName]
    bind_collaborators: Callable[[Any], None] | None = None


__all__ = [
    "BackendAssembly",
    "BackendName",
    "CookieRotator",
    "CookieSaver",
    "SaveCookiesToStorage",
    "installed_backend_map",
]
