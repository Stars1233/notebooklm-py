# Adapter Capability and Hosting Contracts

**Status:** Active baseline  
**Last Updated:** 2026-09-06  
**Source baseline:** `f31f0f9d1db225242ac8f7754f955444b0fcff46`

The CLI, MCP server, and REST server are curated adapters over the same public client and neutral
application workflows. Shared core logic does not imply identical product surfaces. “No” below
describes the exposed surface at this baseline; it is not a commitment to add parity.

## Capability baseline

| Capability | CLI | MCP | REST |
| --- | --- | --- | --- |
| Label management | Yes | Source filtering only; no label-management tools | No routes |
| Collections | Yes | No tools | No routes |
| Live compute usage (`settings.get_usage`) | Yes | No tool | No route |
| Basic account limits and tier | No dedicated command | `server_info` account details | Info response account details |
| Play Books | Yes | `source_list_play_books`, `source_add_play_book` | No routes |
| Chat history | Yes | `chat_ask` with history mode | No route |
| Source search, clean, refresh, and copy | Yes | No exposed verbs | No exposed routes |

The MCP manifest has 38 tools at this baseline. Its serialized schema and descriptions total
44,219 characters against `SCHEMA_CHAR_BUDGET = 44_610`. `tests/unit/mcp/test_manifest.py` pins the
exact manifest and a ceiling of 40; `tests/unit/mcp/test_tool_eval.py` retains the schema and
per-tool parameter ceilings; `tests/e2e/test_mcp.py::TestMcpToolMatrix` maps every registered tool
to owning coverage. A change to the table must follow those live inventories rather than infer
support from similarly named client methods.

REST route modules are explicit under `src/notebooklm/server/routes/`, with route behavior covered
by the corresponding `tests/server/test_*.py` modules. REST remains an experimental local/personal
automation surface. Absence from the table means no supported HTTP route even when the Python
client or another adapter can perform the operation.

## Hosting and persistence limits

Both servers operate one selected NotebookLM account per process. They are single-tenant adapters,
not multi-user credential routers. Restarting the process replaces the lifespan-owned client and
loses ephemeral state.

MCP detached chat tasks are process-owned, bounded, and time-limited. `chat_start` keeps work alive
past one transport request and `chat_status` reads the in-memory result, but a restart loses the
task/result registry. Repeating a still-running semantic request can attach to the existing task;
a completed answer is not replayed as a new conversation turn.

REST pending IDs distinguish a resource created by this process but not yet listable from an ID the
process never created. That provenance is bounded and in-memory. After restart or eviction, a still
pending resource may project as 404 until an authoritative list/read can find it. There is no
durable `/jobs` resource.

MCP upload/download links, completion records, and related pending state are also process-local and
TTL-bounded. A restart invalidates outstanding links and may require the caller to list resources
and begin a new transfer. These limits are part of the experimental hosting contract, not mutation
evidence that authorizes recreating an uncertain upstream resource.

Durable jobs, multi-tenant hosting, more parity tools/routes, or promotion from experimental status
require separate product and security requirements. They are not implied by application-layer reuse.

## Error, timeout, and evidence projection

Adapters may choose presentation vocabulary, but they preserve the neutral operation facts in
[Operation Deadlines, Ownership, and Recovery Contracts](operation-contracts.md): error category or
wire status, `CommitState`, `RecoveryAction`, known resource IDs, ordered batch members, and retry
permission are separate facts.

An HTTP 429, gRPC `RESOURCE_EXHAUSTED`, timeout, cancellation, or generic “retryable” category does
not prove that a dispatched mutation was rejected. Unless a producer supplies stronger correlated
evidence, the commit state stays `UNKNOWN` and the adapter must not turn presentation-level retry
guidance into permission to repeat the mutation.

Configured aggregate operation deadlines already bound queue admission and the complete scoped
workflow on both backends. Web HTTP inactivity/read windows and Android aggregate RPC windows are
inner transport policies. Their expiry does not reset or widen the outer operation deadline. The
default aggregate timeout is `None`; this baseline does not introduce an automatic retry or default
timeout change.

## Evidence owners

| Contract | Executable/source evidence |
| --- | --- |
| CLI capability | Click command groups under `src/notebooklm/cli/`; command and adapter tests under `tests/unit/cli/` |
| MCP exact manifest and budget | `tests/unit/mcp/test_manifest.py`, `tests/unit/mcp/test_tool_eval.py`, `tests/e2e/test_mcp.py` |
| MCP chat history | `src/notebooklm/mcp/tools/chat.py` history branch and MCP chat tests |
| REST route surface | `src/notebooklm/server/routes/` and `tests/server/` |
| Single-tenant/process-lifetime REST provenance | `src/notebooklm/server/_pending.py` and `tests/server/test_hardening.py` |
| Detached MCP task lifetime | `src/notebooklm/mcp/_chattasks.py` and `tests/unit/mcp/test_chat_start.py` |
| Mutation evidence and deadlines | `docs/operation-contracts.md` and its linked implementation/test matrix |
