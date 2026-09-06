# Measured Coupling and Ownership Dispositions

**Status:** C8 audit complete; lazy-barrel change deferred
**Measured:** 2026-09-06  
**Source baseline:** `bd1647fbbba412600710bedcd8fd707c5b90f588`

This audit measures the focused `_app` import cost, checks three candidate shared-policy areas,
and records the ownership map requested by C8. Similar names and root-module count are not evidence
for extraction. A follow-up needs matching preconditions, result/error behavior, and tests before it
moves policy.

C5b moves the canonical download representation registry from `_app.download_specs`
to public `downloads`, retaining compatibility reexports. Backend preparation now
needs the same format/extension/MIME rules as adapters; placing that shared policy
below `_app` avoids an upward dependency. This is an ownership correction, not a
claim of import-time improvement over the measurements below.

## Cold import measurement

Measurements used the repository's shared virtual environment with
`PYTHONPATH=$PWD/src .venv/bin/python` on Darwin 25.6.0 arm64 and Python 3.12.12. Each timing is ten
fresh interpreter processes; the timer surrounds the import statement inside the process. Wall
times are local diagnostic measurements, not performance budgets.

| Fresh import | `_app` modules loaded | `notebooklm` modules loaded | All new modules | Median (min–max) |
| --- | ---: | ---: | ---: | ---: |
| `notebooklm` | 0 | 119 | 439 | 315.536 ms (279.221–692.215) |
| `notebooklm._app` | 31 | 153 | 475 | 389.891 ms (382.089–483.730) |
| `notebooklm._app.resolve` | 31 | 153 | 475 | 396.376 ms (383.000–469.731) |

Importing one focused `_app` submodule executes `_app/__init__.py` first, whose convenience barrel
eagerly imports 30 siblings. The exact `_app` set is:

```text
_app, artifacts, auth_check, chat, collections, doctor, download,
download_specs, errors, events, generate, generate_retry,
generation_requests, labels, language, notebooks, notes, profile,
research, resolve, serialize, session, sharing, skill, source_add,
source_clean, source_content, source_listing, source_mutations,
source_play_books, source_wait
```

**Disposition: defer a lazy-barrel change to a standalone bounded follow-up.** The deterministic graph
delta is 34 `notebooklm` modules and 36 total modules. The timing samples above ran while other
repository validation was active, so they confirm cold-import cost but are not a reliable comparison
with the earlier quiet-worktree numbers. The eager graph is real but low priority beside behavioral
work. `_app.__init__` is a large convenience
re-export surface used throughout adapters/tests, so a correct lazy conversion must preserve symbol
identity, `TYPE_CHECKING` visibility, `__all__`, import-boundary checks, and focused-import behavior.
No evidence here justifies relocating `skill` or `mcp_install`; both are framework-free application
workflows. A follow-up should change only the barrel, add a fresh-process module-count regression,
and leave owner modules in place.

The checked-in runtime coupling audit supplies the broader clean-interpreter
baseline. Run it with:

```bash
PYTHONPATH=$PWD/src .venv/bin/python scripts/audit_backend_coupling.py --mode runtime
```

## Candidate shared-policy inventory

| Candidate | Matching surface | Preconditions/result differences | Evidence | Disposition |
| --- | --- | --- | --- | --- |
| Note existence, update, and readback | `NotesAPI.get/get_or_none/update`; Web and Android implementations; `_app.notes` rename workflow | `_app.notes` already owns adapter-neutral resolve/get-then-update orchestration. Web updates use its note-row service and existence preflight; Android update verifies exact title/content through Android reads and carries gRPC-specific not-found/commit evidence. The wire/readback preconditions are not equivalent. | `tests/unit/test_notes.py`, Android note tests, adapter note workflow tests | **Retain backend implementations.** Shared application orchestration already exists; no further neutral rule is proven. Reassess only with a cross-backend conformance case demonstrating identical preflight and readback semantics. |
| Sharing mutation and readback | `SharingAPI` intent wrappers; Web `_share_and_readback`; Android `set_public`, `set_view_level`, `_mutate_users` | The neutral base already shares `add_user`/`update_user` intent. Web uses batchexecute mutation plus explicit status readback/journal phases. Android uses different RPCs, request messages, and decoded evidence; view-level is not the same Android sharing-service mutation. | sharing unit/parity tests and journal evidence tests | **Retain justified duplication.** Do not extract a generic mutation executor until the same preflight, commit evidence, and readback failure contract is demonstrated for at least two operations on both backends. |
| Source selection and validation | `_app.source_add`, `_source.batch`, `_source.polling`, Web source services, Android source API | URL/path/SSRF and adapter-input rules already live in `_app`; occurrence caps and batch settlement live in `_source.batch`; polling is neutral. Web resumable upload/Drive validation and Android protobuf registration have protocol-specific inputs and failure evidence. | source-add validation tests, batch parity tests, upload/Drive fixtures | **Keep current split.** Existing neutral rules are already extracted. Exclude request construction, row/protobuf parsing, credentials, and transfer stages from a broader merger. |

No candidate supplies evidence for another shared workflow in this audit. The disposition is not a
permanent ban: a future change can add one narrow neutral validation or workflow after its
equivalence matrix exists.

## Ownership map

| Surface | Owner | Boundary |
| --- | --- | --- |
| Public feature namespace contracts | Root private bases such as `_artifacts.py`, `_sources.py`, `_notes.py`, `_sharing.py` | Define backend-neutral signatures, shared intent wrappers, and documentation. They do not encode Web rows or Android protobufs. |
| Neutral artifact mechanisms | `_artifact/downloads.py`, `_artifact/polling.py`, `_artifact/formatters.py`, `_artifact/validation.py` | Transfer mechanics, polling, formatting, and neutral validation. `_artifact.__init__` keeps historical Web service exports lazy. |
| Neutral source mechanisms | `_source/batch.py`, `_source/polling.py`, `_source/drive.py`, `_source/markdown.py` | Batch occurrence/settlement, polling, Drive references, and rendering. `_source.__init__` lazily preserves historical Web service names. |
| Application actions | `_app/<feature>.py` | Framework-free parsing, resolution, multi-step user actions, and typed presentation-neutral results. Adapter frameworks remain outside. |
| Web implementation | `_web/<feature>` and `_web/transport` | Batchexecute rows/codecs, HTTP request construction, Web credential flow, and protocol-specific transfers. |
| Android implementation | `_android/<feature>` and `_android/proto` | Protobuf request/response codecs, gRPC errors/retries, bearer flow, and Android-specific transfers. |
| Operation journal and replay policy | `_idempotency.py` with public projections in `outcomes.py` | Remains below operation context/runtime consumers. Moving it into eager `_runtime` would reverse or inflate the established dependency/import graph. |
| Public exception identity | `exceptions.py` | Canonical public home. Size alone does not justify a split that changes imports or exception identity. |

Root placement is acceptable when the module owns a public namespace contract or a dependency-bottom
mechanism. Move a private module only when an observed dependency or navigation defect is named and
the move preserves provenance, clean imports, public exception identity, and the journal DAG.

## Explicit exclusions

This audit authorizes no line-count split of `exceptions.py`, no edits to auth shrink-locked modules,
no move of journals into `_runtime`, no convergence of backend codecs/error maps/retry manifests,
and no relocation of the shipped curl transport. There are no tracked files under a
`src/notebooklm/services/` package to clean up, and untracked caches are outside repository work.
