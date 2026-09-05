"""Unit coverage for the transport-neutral live usage API."""

from datetime import datetime, timedelta, timezone

import pytest

from notebooklm._settings import SettingsAPI
from notebooklm._usage import (
    RawUsageAction,
    RawUsageSummary,
    RawUsageWindow,
    UsageAccount,
    decode_usage_summary,
)
from notebooklm.exceptions import DecodingError, ServerError
from notebooklm.types import (
    AccountLimits,
    UsageActionCostTier,
    UsageActionKind,
    UsageSummary,
    UsageSummaryStatus,
    UsageWindowKind,
    UserSettings,
)

RESET = datetime(2026, 9, 5, 14, tzinfo=timezone.utc)


def _window(
    code: int | None,
    *,
    used: float | None = 10.0,
    remaining: float | None = 90.0,
    resets_at: datetime | None = RESET,
) -> RawUsageWindow:
    return RawUsageWindow(code, resets_at, used, remaining)


def _action(
    code: int | None = 9,
    *,
    sufficient: bool | None = True,
    tier: int | None = 2,
    deferred: int | None = 3,
    cost: float | None = 1.5,
) -> RawUsageAction:
    return RawUsageAction(code, sufficient, tier, deferred, cost)


def _ready(*, windows: tuple[RawUsageWindow, ...] | None = None, actions=()) -> RawUsageSummary:
    return RawUsageSummary(
        status_code=1,
        windows=(_window(1), _window(2)) if windows is None else windows,
        actions=actions,
    )


def test_public_usage_models_are_available_from_both_facades():
    import notebooklm

    assert notebooklm.UsageSummary is UsageSummary
    assert notebooklm.UsageActionKind is UsageActionKind
    assert UsageActionKind.SUGGESTION_CHIPS.value == 22
    assert UsageActionCostTier.VERY_HIGH.value == 4


def test_usage_action_kind_uses_the_exact_server_code_map():
    assert [(kind.name, kind.value) for kind in UsageActionKind] == [
        ("AUDIO_OVERVIEW", 1),
        ("VIDEO_OVERVIEW", 2),
        ("BREAKDOWNS_VIDEO", 3),
        ("SHORTS_VIDEO", 4),
        ("INFOGRAPHIC", 5),
        ("SLIDES", 6),
        ("REPORTS", 7),
        ("TABLES", 8),
        ("FLASHCARDS", 9),
        ("QUIZ", 10),
        ("MINDMAP", 11),
        ("CANVAS", 12),
        ("SLIDES_EDITING", 13),
        ("FLASHCARD_EDITING", 14),
        ("DEEP_RESEARCH", 15),
        ("NOS", 16),
        ("FAST_RESEARCH", 17),
        ("QNA", 18),
        ("NOS_IMAGE_GENERATION", 19),
        ("GUIDED_VIEW", 20),
        ("DOCUMENT_GUIDE", 21),
        ("SUGGESTION_CHIPS", 22),
    ]


def test_usage_summary_conveniences_follow_ui_window_selection():
    ready = decode_usage_summary(
        _ready(windows=(_window(2, used=100.0, remaining=0.0), _window(1, used=30.0)))
    )

    assert ready.enabled is True
    assert ready.available is True
    assert ready.window(UsageWindowKind.FIVE_HOUR).used_percent == 30.0  # type: ignore[union-attr]
    assert ready.active_window == ready.window(UsageWindowKind.WEEKLY)
    assert ready.is_exhausted is True

    disabled = UsageSummary(UsageSummaryStatus.DISABLED)
    skipped = UsageSummary(UsageSummaryStatus.SKIPPED)
    assert disabled.enabled is False
    assert disabled.available is False
    assert disabled.active_window is None
    assert disabled.is_exhausted is None
    assert skipped.enabled is True
    assert skipped.available is False
    assert skipped.is_exhausted is None


@pytest.mark.parametrize("status", [None, 0, 4])
def test_decode_rejects_missing_zero_or_unknown_status(status):
    with pytest.raises(DecodingError, match="status") as error:
        decode_usage_summary(RawUsageSummary(status_code=status))
    assert error.value.method_id == "ListQuotaSummary"


def test_decode_skipped_ignores_any_payload_and_failed_is_server_error():
    assert decode_usage_summary(_ready()).status is UsageSummaryStatus.READY
    skipped = decode_usage_summary(RawUsageSummary(status_code=2, windows=(_window(99),)))
    assert skipped == UsageSummary(UsageSummaryStatus.SKIPPED)

    with pytest.raises(ServerError, match="failed") as error:
        decode_usage_summary(RawUsageSummary(status_code=3, method_id="native/ListQuotaSummary"))
    assert error.value.method_id == "native/ListQuotaSummary"


@pytest.mark.parametrize(
    "windows",
    [
        (),
        (_window(1),),
        (_window(1), _window(1)),
        (_window(1), _window(3)),
    ],
    ids=["missing", "weekly-missing", "duplicate", "unknown"],
)
def test_decode_requires_exactly_one_known_window_of_each_kind(windows):
    with pytest.raises(DecodingError, match="window"):
        decode_usage_summary(_ready(windows=windows))


def test_decode_window_elision_non_complementary_values_and_utc_normalization():
    eastern = timezone(timedelta(hours=-4))
    summary = decode_usage_summary(
        _ready(
            windows=(
                _window(2, used=None, remaining=40.0, resets_at=RESET.astimezone(eastern)),
                _window(1, used=12.25, remaining=None),
            )
        )
    )

    five_hour = summary.window(UsageWindowKind.FIVE_HOUR)
    weekly = summary.window(UsageWindowKind.WEEKLY)
    assert five_hour is not None and (five_hour.used_percent, five_hour.remaining_percent) == (
        12.25,
        87.75,
    )
    assert weekly is not None
    assert (weekly.used_percent, weekly.remaining_percent, weekly.resets_at) == (60.0, 40.0, RESET)

    non_complementary = decode_usage_summary(
        _ready(windows=(_window(1, used=11.0, remaining=12.0), _window(2)))
    )
    assert non_complementary.window(UsageWindowKind.FIVE_HOUR).remaining_percent == 12.0  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "windows",
    [
        (_window(1, used=None, remaining=None), _window(2)),
        (_window(1, used=float("nan")), _window(2)),
        (_window(1), _window(2, remaining=float("inf"))),
        (_window(1, used=10**400), _window(2)),
        (_window(1, resets_at=datetime(2026, 9, 5)), _window(2)),
    ],
    ids=[
        "both-percentages-absent",
        "nan-used",
        "infinite-remaining",
        "oversized-used",
        "naive-timestamp",
    ],
)
def test_decode_rejects_invalid_window_fields(windows):
    with pytest.raises(DecodingError):
        decode_usage_summary(_ready(windows=windows))


def test_decode_actions_normalizes_optional_values_preserves_future_and_sorts():
    summary = decode_usage_summary(
        _ready(
            actions=(_action(23, sufficient=None, tier=99, deferred=None, cost=None), _action(9))
        )
    )

    assert [action.code for action in summary.actions] == [9, 23]
    future = summary.action(23)
    assert future is not None
    assert future.kind is None
    assert future.has_sufficient_quota is False
    assert future.cost_tier is None
    assert future.remaining_deferred_artifact_generations is None
    assert future.estimated_cost_percent is None
    assert summary.action(UsageActionKind.FLASHCARDS).cost_tier is UsageActionCostTier.MEDIUM  # type: ignore[union-attr]

    zero_tier = decode_usage_summary(_ready(actions=(_action(tier=0),))).actions[0]
    assert zero_tier.cost_tier is None


@pytest.mark.parametrize(
    "action",
    [
        _action(None),
        _action(0),
        _action(deferred=-1),
        _action(cost=float("nan")),
        _action(cost=float("inf")),
        _action(cost=10**400),
    ],
    ids=[
        "missing-code",
        "zero-code",
        "negative-deferred",
        "nan-cost",
        "infinite-cost",
        "oversized-cost",
    ],
)
def test_decode_rejects_invalid_action_fields(action):
    with pytest.raises(DecodingError):
        decode_usage_summary(_ready(actions=(action,)))


class _Settings(SettingsAPI):
    def __init__(self, account: UsageAccount, summary: RawUsageSummary) -> None:
        self.account = account
        self.summary = summary
        self.account_calls = 0
        self.summary_calls = 0

    async def set_output_language(self, language: str) -> str | None:
        return language

    async def get_user_settings(self) -> UserSettings:
        return UserSettings()

    async def get_output_language(self) -> str | None:
        return None

    async def get_account_limits(self) -> AccountLimits:
        return AccountLimits()

    async def _get_usage_account(self, *, lease: object) -> UsageAccount:
        self.account_calls += 1
        return self.account

    async def _list_quota_summary(self, *, lease: object) -> RawUsageSummary:
        self.summary_calls += 1
        return self.summary


@pytest.mark.asyncio
async def test_get_usage_uses_account_bit_to_skip_summary_call():
    api = _Settings(UsageAccount(False), _ready())

    assert await api.get_usage() == UsageSummary(UsageSummaryStatus.DISABLED)
    assert (api.account_calls, api.summary_calls) == (1, 0)


@pytest.mark.asyncio
async def test_get_usage_calls_live_summary_when_enabled():
    api = _Settings(UsageAccount(True), _ready(actions=(_action(),)))

    summary = await api.get_usage()

    assert summary.status is UsageSummaryStatus.READY
    assert summary.actions[0].kind is UsageActionKind.FLASHCARDS
    assert (api.account_calls, api.summary_calls) == (1, 1)
