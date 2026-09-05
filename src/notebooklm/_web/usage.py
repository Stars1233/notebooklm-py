"""Web positional codecs for the live compute-meter usage RPCs.

The public usage models deliberately live outside the Web backend.  This
module only translates the batchexecute arrays into the neutral bridge records
owned by :mod:`notebooklm._usage`; keeping that boundary here makes the same
semantic validation usable by the Web and Android adapters.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from ..exceptions import DecodingError
from ..rpc import RPCMethod

if TYPE_CHECKING:
    from .._runtime.call_supervisor import OperationLease
    from .._usage import RawUsageAction, RawUsageSummary, RawUsageWindow, UsageAccount
    from .contracts import RpcCaller

_ACCOUNT_METHOD_ID = RPCMethod.GET_ACCOUNT.value
_QUOTA_METHOD_ID = RPCMethod.LIST_QUOTA_SUMMARY.value


def _bridge_types() -> tuple[type[Any], type[Any], type[Any], type[Any], type[Any]]:
    """Load neutral bridge records only when a usage call is made.

    The public branch supplies ``_usage`` alongside this adapter.  Lazy import
    avoids making unrelated legacy Web settings imports depend on that branch
    while the transport changes are developed independently.
    """

    from .._usage import (  # noqa: PLC0415
        RawUsageAction,
        RawUsageSummary,
        RawUsageWindow,
        UsageAccount,
    )

    return UsageAccount, RawUsageSummary, RawUsageWindow, RawUsageAction, datetime


def build_get_account_params() -> list[Any]:
    """Build the empty Web request for ``GetAccount``."""

    return []


def build_list_quota_summary_params() -> list[Any]:
    """Build ``ListQuotaSummary([RequestContext])`` for batchexecute.

    Web's request-context slot is represented by the usual ``null`` value;
    unlike the Android transport, there is no local protobuf object to build.
    """

    return [None]


def _error(message: str, *, method_id: str) -> DecodingError:
    return DecodingError(message, method_id=method_id)


def _slot(value: Any, index: int) -> Any:
    """Return an array slot, preserving protobuf-style elision as ``None``."""

    return value[index] if isinstance(value, list) and 0 <= index < len(value) else None


def _optional_number(value: Any, *, method_id: str, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _error(f"{label} is not numeric", method_id=method_id)
    number = float(value)
    if not math.isfinite(number):
        raise _error(f"{label} is non-finite", method_id=method_id)
    return number


def _optional_int(value: Any, *, method_id: str, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _error(f"{label} is not integral", method_id=method_id)
    return value


def _timestamp(value: Any, *, method_id: str) -> datetime | None:
    """Decode a JSPB Timestamp represented as ``[seconds, nanos]``.

    A few Web decoder versions have emitted an RFC3339 string while the
    current array codec emits the protobuf pair.  Accept both wire-equivalent
    representations, but reject malformed present values so drift is not
    mistaken for a missing reset time.
    """

    if value is None:
        return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise _error("invalid quota reset timestamp", method_id=method_id) from exc
        if parsed.tzinfo is None:
            raise _error("quota reset timestamp is naive", method_id=method_id)
        return parsed.astimezone(timezone.utc)
    if not isinstance(value, list) or not value:
        raise _error("invalid quota reset timestamp", method_id=method_id)
    seconds = value[0]
    nanos = value[1] if len(value) > 1 and value[1] is not None else 0
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise _error("quota reset timestamp seconds is not numeric", method_id=method_id)
    if isinstance(nanos, bool) or not isinstance(nanos, (int, float)):
        raise _error("quota reset timestamp nanos is not numeric", method_id=method_id)
    if not math.isfinite(float(seconds)) or not math.isfinite(float(nanos)):
        raise _error("quota reset timestamp is non-finite", method_id=method_id)
    if not float(nanos).is_integer() or not 0 <= int(nanos) < 1_000_000_000:
        raise _error("quota reset timestamp nanos is invalid", method_id=method_id)
    try:
        return datetime.fromtimestamp(float(seconds), tz=timezone.utc) + timedelta(
            microseconds=int(nanos) / 1_000
        )
    except (OverflowError, OSError, ValueError) as exc:
        raise _error("quota reset timestamp is out of range", method_id=method_id) from exc


def decode_account(data: Any) -> UsageAccount:
    """Extract ``PremiumUserInfo.computeMeteringEnabled`` from GetAccount.

    ``GetAccount`` is an account envelope (field 1 in the native equivalent),
    while the Web response has appeared both as ``[account]`` and as a direct
    account array.  The field path inside the account is stable: account f5,
    premium-user-info f7.  Absent account/field and an explicit false all map
    to the neutral account's false default, as required by ADR-0037.
    """

    UsageAccount, _, _, _, _ = _bridge_types()
    candidates: list[Any] = [data]
    if isinstance(data, list) and data:
        candidates.append(data[0])
        if isinstance(data[0], list) and data[0]:
            candidates.append(data[0][0])
    enabled = False
    for account in candidates:
        premium = _slot(account, 4)
        value = _slot(premium, 6)
        if isinstance(value, bool):
            enabled = value
            break
    return UsageAccount(compute_metering_enabled=enabled)


def _decode_window(row: Any) -> RawUsageWindow:
    _, _, RawUsageWindow, _, _ = _bridge_types()
    if not isinstance(row, list):
        raise _error("quota window row is not an array", method_id=_QUOTA_METHOD_ID)
    return RawUsageWindow(
        window_code=_optional_int(
            _slot(row, 4), method_id=_QUOTA_METHOD_ID, label="quota window code"
        ),
        resets_at=_timestamp(_slot(row, 5), method_id=_QUOTA_METHOD_ID),
        used_percent=_optional_number(
            _slot(row, 6), method_id=_QUOTA_METHOD_ID, label="quota used percentage"
        ),
        remaining_percent=_optional_number(
            _slot(row, 7), method_id=_QUOTA_METHOD_ID, label="quota remaining percentage"
        ),
    )


def _decode_action(row: Any) -> RawUsageAction:
    _, _, _, RawUsageAction, _ = _bridge_types()
    if not isinstance(row, list):
        raise _error("quota action row is not an array", method_id=_QUOTA_METHOD_ID)
    action_code = _optional_int(
        _slot(row, 0), method_id=_QUOTA_METHOD_ID, label="quota action code"
    )
    has_quota = _slot(row, 1)
    if has_quota is not None and not isinstance(has_quota, bool):
        raise _error("quota availability is not boolean", method_id=_QUOTA_METHOD_ID)
    deferred = _slot(row, 2)
    if deferred is not None and (
        isinstance(deferred, bool) or not isinstance(deferred, int) or deferred < 0
    ):
        raise _error("remaining deferred generations is invalid", method_id=_QUOTA_METHOD_ID)
    cost_tier = _slot(row, 3)
    if cost_tier is not None and (isinstance(cost_tier, bool) or not isinstance(cost_tier, int)):
        raise _error("quota cost tier is not integral", method_id=_QUOTA_METHOD_ID)
    return RawUsageAction(
        action_code=action_code,
        has_sufficient_quota=has_quota,
        cost_tier_code=cost_tier,
        remaining_deferred_artifact_generations=deferred,
        estimated_cost_percent=_optional_number(
            _slot(row, 5), method_id=_QUOTA_METHOD_ID, label="estimated quota cost"
        ),
    )


def decode_quota_summary(data: Any) -> RawUsageSummary:
    """Decode ``ListQuotaSummary`` response fields f1, f2, and f4."""

    _, RawUsageSummary, _, _, _ = _bridge_types()
    if not isinstance(data, list):
        raise _error("quota summary response is not an array", method_id=_QUOTA_METHOD_ID)
    windows_data = _slot(data, 1)
    actions_data = _slot(data, 3)
    if windows_data is None:
        windows: tuple[Any, ...] = ()
    elif isinstance(windows_data, list):
        windows = tuple(_decode_window(row) for row in windows_data)
    else:
        raise _error("quota windows field is not an array", method_id=_QUOTA_METHOD_ID)
    if actions_data is None:
        actions: tuple[Any, ...] = ()
    elif isinstance(actions_data, list):
        actions = tuple(_decode_action(row) for row in actions_data)
    else:
        raise _error("quota actions field is not an array", method_id=_QUOTA_METHOD_ID)
    status = _optional_int(_slot(data, 0), method_id=_QUOTA_METHOD_ID, label="quota status")
    return RawUsageSummary(
        status_code=status,
        windows=windows,
        actions=actions,
        method_id=_QUOTA_METHOD_ID,
    )


async def get_usage_account(rpc: RpcCaller, *, lease: OperationLease | None = None) -> UsageAccount:
    """Issue an uncached live GetAccount read and decode its account bit."""

    del lease  # Web RPC caller has no epoch argument; retained for backend parity.
    return decode_account(
        await rpc.rpc_call(RPCMethod.GET_ACCOUNT, build_get_account_params(), source_path="/")
    )


async def list_quota_summary(
    rpc: RpcCaller, *, lease: OperationLease | None = None
) -> RawUsageSummary:
    """Issue an uncached live ListQuotaSummary read and decode its payload."""

    del lease
    return decode_quota_summary(
        await rpc.rpc_call(
            RPCMethod.LIST_QUOTA_SUMMARY,
            build_list_quota_summary_params(),
            source_path="/",
        )
    )


__all__ = [
    "build_get_account_params",
    "build_list_quota_summary_params",
    "decode_account",
    "decode_quota_summary",
    "get_usage_account",
    "list_quota_summary",
]
