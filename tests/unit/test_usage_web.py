"""Focused Web transport tests for the live usage-meter RPCs."""

from unittest.mock import AsyncMock

import pytest

pytest.importorskip("notebooklm._usage")

from notebooklm._web.usage import (  # noqa: E402
    build_get_account_params,
    build_list_quota_summary_params,
    decode_account,
    decode_quota_summary,
    get_usage_account,
    list_quota_summary,
)
from notebooklm.exceptions import DecodingError  # noqa: E402
from notebooklm.rpc import RPCMethod  # noqa: E402


def test_usage_request_shapes_are_wire_exact() -> None:
    assert build_get_account_params() == []
    assert build_list_quota_summary_params() == [None]


def test_decode_account_reads_nested_compute_metering_bit() -> None:
    enabled = decode_account([[None, None, None, None, [None, None, None, None, None, None, True]]])
    disabled = decode_account([])

    assert enabled.compute_metering_enabled is True
    assert disabled.compute_metering_enabled is False


def test_decode_quota_summary_preserves_optional_fields_and_timestamp() -> None:
    result = decode_quota_summary(
        [
            1,
            [[None, None, None, None, 2, [1700604800, 0], None, 99.9]],
            None,
            [[9, True, 3, 2, None, 1.8666666667]],
        ]
    )

    assert result.status_code == 1
    assert result.windows[0].window_code == 2
    assert result.windows[0].used_percent is None
    assert result.windows[0].remaining_percent == 99.9
    assert result.windows[0].resets_at is not None
    assert result.windows[0].resets_at.tzinfo is not None
    assert result.actions[0].action_code == 9
    assert result.actions[0].remaining_deferred_artifact_generations == 3


def test_decode_quota_summary_rejects_non_finite_percentages() -> None:
    with pytest.raises(DecodingError, match="non-finite") as raised:
        decode_quota_summary(
            [1, [[None, None, None, None, 1, [1700000000, 0], float("nan"), 100.0]], None, []]
        )
    assert raised.value.method_id == RPCMethod.LIST_QUOTA_SUMMARY.value


@pytest.mark.asyncio
async def test_usage_calls_are_live_rpc_reads() -> None:
    rpc = AsyncMock(
        side_effect=[
            [[None, None, None, None, [None, None, None, None, None, None, True]]],
            [2, [], None, []],
        ]
    )

    account = await get_usage_account(rpc)
    summary = await list_quota_summary(rpc)

    assert account.compute_metering_enabled is True
    assert summary.status_code == 2
    assert [call.args[:2] for call in rpc.call_args_list] == [
        (RPCMethod.GET_ACCOUNT, []),
        (RPCMethod.LIST_QUOTA_SUMMARY, [None]),
    ]
