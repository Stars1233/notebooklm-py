# Application action ownership

Application executors use the public operation boundary from their first client-dependent await
through required readback and result construction. Resolution, mutation, retry, and optional waiting
share one admitted generation and cumulative budget. An operation provides lifetime and evidence
consistency; it does not make server-side read-modify-write transactional.

```python
from notebooklm.options import USE_DEFAULT

async with client.operation(timeout=USE_DEFAULT):
    notebook = await client.notebooks.create("Research")
    await client.sources.add_url(notebook.id, "https://example.com")
```

`USE_DEFAULT` (typed by public `notebooklm.options.UseDefault`) inherits the task-owned enclosing
operation, or uses `ClientConfig.runtime.operation_timeout` if no operation exists. The configured
default remains `None`. Existing `client.operation()` and explicit `timeout=None` remain unbounded
when top-level; nested scopes can only shorten their parent's deadline. Stage timeouts remain inner
bounds and do not restart the aggregate budget.

Graceful drain rejects unrelated actions while allowing an admitted action's dependent steps to
finish. Forced close and reopen fence continuation from the old generation. Shared refresh, polling,
and lazy-open producers retain their independent ownership and outlive an individual waiter where
already supported. User confirmation takes place before the execution scope; login, profile repair,
and package administration do not acquire a client operation.

## Application inventory

The C2 audit combined an AST inventory of client-dependent awaits with manual call-chain review:

| Executors | Owned span |
| --- | --- |
| Generation | Notebook/source resolution, create/retry, optional completion wait, result |
| Download | Resolve, list/select, all selected transfers, publication, results |
| Source research and research wait | Start or resolve, wait, optional import, result |
| Chat configure/history/save-note | Read-dependent update, conversation lookup/history, note save/result |
| Source mutations/Drive/add | Approved inputs or preflight, mutation, namespace readiness/readback, result |
| Source cleanup | Approved immutable IDs, supervised deletion children, settlement, ordered evidence |
| Notes and notebooks | Resolve, mutation/readback, timestamp enrichment or dependent reads, result |
| Labels, collections, sharing | Namespace operation and required result/readback |
| Source listing/content and notebook selection | Filter/reference resolution and dependent reads |

Single-read helpers and namespace-owned polling retain their existing operation scopes. Cleanup
preview and deletion have separate scopes so interactive confirmation cannot keep admission open.

## Supervised source cleanup

`client.sources.delete_many_with_outcomes(notebook_id, source_ids)` returns an ordered list of frozen
`SourceDeleteOutcome` records, imported from `notebooklm.types` or `notebooklm`. Each contains the
source ID, canonical `BatchItemOutcome`, and an optional original failure. Input occurrences are
preserved. `CONFIRMED`, `REJECTED`, `UNKNOWN`, and `NOT_SENT` are evidence states, not guesses from
HTTP status. Unknown outcomes retain reconciliation details. Records reuse the existing bounded
batch metadata contract.

Cleanup admits at most ten exclusive children at a time and preserves the half-second pause between
groups. Children inherit the parent's deadline and journal. Cancellation settles active children,
retains confirmed siblings and unattempted members on the escaping error, and remains cancellation.
An aggregate deadline produces `OperationTimeoutError` with that settlement evidence intact.
Existing `delete_many() -> None` retains its separate deduplication and backend wire semantics.

Research timeout, download, and optional note-save results retain original failures in typed fields
so exception-to-result projection does not discard commit evidence. Adapter-facing error text is
bounded and redacted. A successful earlier mutation remains evidence when a later step fails; callers
must inspect known IDs rather than replay the whole action.

Regression coverage lives in `test_app_operation_scopes.py`, `test_source_delete_outcomes.py`, and
`test_operation_context.py`, alongside the existing application and CLI behavior suites. Tests use
real application/supervisor or namespace orchestration with fake I/O terminals; no live captures are
needed for admission, deadline, or settlement contracts.
