"""Application actions exercise the real client operation context and supervisor."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from notebooklm import NotebookLMClient, OperationTimeoutError
from notebooklm._app.chat import execute_configure, fetch_history
from notebooklm._client_metrics import ClientMetrics
from notebooklm._runtime.call_supervisor import CallSupervisor
from notebooklm._runtime.operation_context import current_operation_context
from notebooklm.options import USE_DEFAULT
from notebooklm.types import ChatGoal, ChatResponseLength, ChatSettings

pytestmark = pytest.mark.asyncio


def _client(timeout: float | None = None) -> tuple[NotebookLMClient, CallSupervisor]:
    supervisor = CallSupervisor(
        metrics=ClientMetrics(), max_concurrent_rpcs=1, operation_timeout=timeout
    )
    supervisor.prepare_generation(1)
    supervisor.start_accepting(1)
    client = object.__new__(NotebookLMClient)
    client._collaborators = SimpleNamespace(call_supervisor=supervisor)
    return client, supervisor


async def test_public_default_selector_inherits_configured_budget() -> None:
    client, supervisor = _client(0.01)
    with pytest.raises(OperationTimeoutError):
        async with client.operation(timeout=USE_DEFAULT):
            await asyncio.Event().wait()
    async with client.operation():
        assert current_operation_context(supervisor).absolute_deadline is None
    async with client.operation(timeout=None):
        assert current_operation_context(supervisor).absolute_deadline is None


async def test_default_selector_preserves_parent_context_and_shorter_deadline() -> None:
    client, supervisor = _client(0.001)
    async with client.operation(timeout=None):
        parent = current_operation_context(supervisor)
        async with client.operation(timeout=USE_DEFAULT):
            assert current_operation_context(supervisor) is parent
            await asyncio.sleep(0.01)
    # This verifies inheritance and shortening, not timer expiry. Keep the
    # deadlines beyond platform timer resolution and CI scheduling jitter.
    async with client.operation(timeout=60.0):
        parent = current_operation_context(supervisor)
        async with client.operation(timeout=USE_DEFAULT):
            assert current_operation_context(supervisor) is parent
        async with client.operation(timeout=30.0):
            child = current_operation_context(supervisor)
            assert child.absolute_deadline < parent.absolute_deadline
        assert current_operation_context(supervisor) is parent


async def test_history_steps_share_one_budget_and_expire_before_second_dispatch() -> None:
    client, supervisor = _client(0.015)
    calls = []

    async def conversation_id(notebook_id):
        async with supervisor.operation_scope("chat.id"):
            calls.append("id")
            await asyncio.sleep(0.01)
            return "conversation"

    async def history(notebook_id, **kwargs):
        async with supervisor.operation_scope("chat.history"):
            await asyncio.sleep(0.01)
            async with supervisor.call_scope("history.dispatch", None, None):
                calls.append("history")
            return []

    client.chat = SimpleNamespace(get_conversation_id=conversation_id, get_history=history)
    with pytest.raises(OperationTimeoutError):
        await fetch_history(client, "nb", limit=3)
    assert calls == ["id"]


async def test_configure_remains_admitted_between_steps_during_drain() -> None:
    client, supervisor = _client()
    read = asyncio.Event()
    resume = asyncio.Event()
    updated = []

    async def settings(notebook_id):
        async with supervisor.operation_scope("chat.settings"):
            read.set()
            await resume.wait()
            return ChatSettings(ChatGoal.DEFAULT, ChatResponseLength.LONGER, None)

    async def configure(notebook_id, **kwargs):
        async with supervisor.operation_scope("chat.configure"):
            updated.append(kwargs)

    client.chat = SimpleNamespace(get_settings=settings, configure=configure)
    action = asyncio.create_task(
        execute_configure(client, "nb", chat_mode=None, persona="new persona", response_length=None)
    )
    await read.wait()
    await supervisor.stop_accepting(1)
    draining = asyncio.create_task(supervisor.wait_for_idle(1, timeout=None))
    await asyncio.sleep(0)
    with pytest.raises(RuntimeError):
        async with client.operation(timeout=USE_DEFAULT):
            pass
    assert not draining.done()
    resume.set()
    await action
    await draining
    assert updated[0]["response_length"] is ChatResponseLength.LONGER


async def test_retired_application_cannot_continue_after_reopen() -> None:
    client, supervisor = _client()
    read = asyncio.Event()
    resume = asyncio.Event()
    dispatched = []

    async def conversation_id(notebook_id):
        read.set()
        await resume.wait()
        return "conversation"

    async def history(notebook_id, **kwargs):
        async with supervisor.operation_scope("chat.history"):
            dispatched.append(notebook_id)
            return []

    client.chat = SimpleNamespace(get_conversation_id=conversation_id, get_history=history)
    action = asyncio.create_task(fetch_history(client, "nb", limit=3))
    await read.wait()
    await supervisor.begin_closing(1)
    supervisor.mark_closed(1)
    supervisor.prepare_generation(2)
    supervisor.start_accepting(2)
    resume.set()
    with pytest.raises(RuntimeError):
        await action
    assert dispatched == []


async def test_saved_note_failure_retains_commit_evidence():
    from notebooklm import RPCError
    from notebooklm._app.chat import save_answer_as_note
    from notebooklm._idempotency import attach_operation_metadata
    from notebooklm.outcomes import CommitState, OperationMetadata, ReconciliationReport
    from notebooklm.types import AskResult

    client, supervisor = _client()
    failure = RPCError("save was interrupted")
    attach_operation_metadata(
        failure,
        OperationMetadata(
            commit_state=CommitState.UNKNOWN,
            known_resource_ids=("note-accepted",),
            reconciliation=ReconciliationReport(
                unresolved_inputs=("note",), reason="readback failed"
            ),
        ),
    )

    async def create(*args):
        raise failure

    client.notes = SimpleNamespace(create=create)
    result = await save_answer_as_note(
        client,
        "nb",
        AskResult(answer="answer", conversation_id="c", turn_number=1, is_follow_up=False),
        note_title=None,
        question="question",
    )
    assert result.failure is failure
    assert result.failure.operation_metadata.known_resource_ids == ("note-accepted",)
    await supervisor.wait_for_idle(1, 0)


async def test_saved_note_owned_timeout_returns_settled_commit_evidence():
    from notebooklm._app.chat import save_answer_as_note
    from notebooklm._runtime.operation_context import adopt_operation_journal_entry
    from notebooklm.outcomes import CommitState
    from notebooklm.types import AskResult

    client, supervisor = _client(0.01)

    async def create(*args):
        entry = adopt_operation_journal_entry(
            supervisor, method="CREATE_NOTE", operation="notes.create"
        )
        assert entry is not None
        entry.mark_dispatched()
        entry.record(
            CommitState.CONFIRMED,
            "decoded creation response",
            known_resource_ids=("note-created",),
        )
        # The note exists, but required readback has not completed when the
        # real operation timer expires. Saving remains an optional action.
        await asyncio.Event().wait()

    client.notes = SimpleNamespace(create=create)
    outcome = await save_answer_as_note(
        client,
        "nb",
        AskResult(answer="answer", conversation_id="c", turn_number=1, is_follow_up=False),
        note_title=None,
        question="question",
    )

    assert outcome.note is None
    assert outcome.error
    assert isinstance(outcome.failure, OperationTimeoutError)
    metadata = outcome.failure.operation_metadata
    assert metadata is not None
    assert metadata.commit_state is CommitState.CONFIRMED
    assert metadata.known_resource_ids == ("note-created",)
    assert metadata.entries[0].operation == "notes.create"
    await supervisor.wait_for_idle(1, 0)


async def test_saved_note_external_cancellation_propagates():
    from notebooklm._app.chat import save_answer_as_note
    from notebooklm.types import AskResult

    client, supervisor = _client()
    started = asyncio.Event()

    async def create(*args):
        started.set()
        await asyncio.Event().wait()

    client.notes = SimpleNamespace(create=create)
    action = asyncio.create_task(
        save_answer_as_note(
            client,
            "nb",
            AskResult(answer="answer", conversation_id="c", turn_number=1, is_follow_up=False),
            note_title=None,
            question="question",
        )
    )
    await started.wait()
    action.cancel()
    with pytest.raises(asyncio.CancelledError):
        await action
    await supervisor.wait_for_idle(1, 0)
