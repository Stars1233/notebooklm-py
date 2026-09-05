"""Small import leaf for infrastructure shared by the MCP and REST adapters.

This module is intentionally outside :mod:`notebooklm._app`: the exported
values support transport hosting rather than transport-neutral business logic.
"""

from ._loop_bound import LoopBoundPrimitive
from ._redact import redact
from ._runtime.config import DEFAULT_SERVER_KEEPALIVE_INTERVAL
from ._serving import (
    LOOPBACK_HOSTNAMES,
    addr_is_loopback,
    check_bind_allowed,
    host_header_is_loopback,
    is_loopback,
)

__all__ = [
    "DEFAULT_SERVER_KEEPALIVE_INTERVAL",
    "LOOPBACK_HOSTNAMES",
    "LoopBoundPrimitive",
    "addr_is_loopback",
    "check_bind_allowed",
    "host_header_is_loopback",
    "is_loopback",
    "redact",
]
