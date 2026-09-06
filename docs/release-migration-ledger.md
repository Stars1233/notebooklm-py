# Release Migration Ledger

**Status:** Active audit; no breaking change is authorized by this document  
**Audited:** 2026-09-06  
**Source baseline:** `f31f0f9d1db225242ac8f7754f955444b0fcff46`

This ledger separates a migration's design state from its release eligibility. An accepted ADR,
source warning, test registry row, changelog draft, or version comment proves design or runway
preparation only. Eligibility requires the notice or preview to exist in an actual published stable
release, followed by the interval required by [stability policy](stability.md#deprecation-policy).
Each transition owns its own evidence; rows cannot borrow another migration's release date.

The existing v1 inventory below is an exact one-for-one ledger of all 34 entries in
`tests/_guardrails/_v100_breaks.py`. Keep that registry and this table complete until the release
cut drains both deliberately. The additional credential and C3/C4/C5 rows record migrations the
v1 registry did not yet express at the audit baseline.

## Published release evidence

The audit used the GitHub release list, remote tag refs, and the files served from those tag refs.

| Release | Published evidence | Source evidence relevant here |
| --- | --- | --- |
| v0.5.0 | [GitHub release, 2026-05-24](https://github.com/teng-lin/notebooklm-py/releases/tag/v0.5.0), commit `7621088c03a804fbdf4c8b5959bd9a9faafcc4c6` | The changelog and `client.py` ship the warning for awaiting `NotebookLMClient.from_storage(...)`. |
| v0.8.1 | [GitHub release, 2026-08-14](https://github.com/teng-lin/notebooklm-py/releases/tag/v0.8.1), remote tag `01c419a0474e0191b88e94c572d605b4899a9c2b` | Tagged `_deprecation.py` ships the three registered `AuthTokens` warnings; tagged deprecation docs ship the Web cookie-field, home-root, citation, and notebook-name runways. |
| v0.8.2 | [GitHub release, 2026-09-02](https://github.com/teng-lin/notebooklm-py/releases/tag/v0.8.2), remote tag `c1008a4416e338b7497a7db7db0500fad5f097e6` | Latest stable release at audit time. It continues the v0.8.1 runways but predates the P5/P6/P7 warning work merged later. |
| v0.9.0 | **No GitHub release and no remote tag at audit time.** | Every current row whose registry or docs says `Since = 0.9.0` is unshipped. Source text does not satisfy its gate. |

For a migration first shipped in v0.8.1 or earlier and scheduled for the next major, the earliest
eligible release is v1.0.0. For a staged v0.9.0 migration, v1.0.0 is only conditionally earliest:
a stable v0.9.0 containing that exact warning must publish first, and C9b cannot be the same release
that first introduces the warning. New 0.x transitions retain their compatibility paths until their
own stable notice release and required interval have elapsed, even if that is later than v1.0.0.

## C9 credential-surface decisions outside the original registry

[ADR-0039](adr/0039-backend-specific-credential-surfaces.md) settles the destination. These rows
remain release-ineligible because the 0.x surface does not yet warn users about the corresponding
Android/client-auth changes.

| ID | Transition | Owner | Class | First shipped notice | Earliest eligible transition | Gate and guardrail disposition |
| --- | --- | --- | --- | --- | --- | --- |
| C9-CRED-01 | Direct Android construction changes from Web `AuthTokens` to public `AndroidMasterToken`; mismatches fail before I/O. | C9 | API + behavior | None | After its own stable notice release and interval | **Not met.** Add a registered constructor migration and API signature allowances only with the actual cut. |
| C9-CRED-02 | `client.auth` becomes `AuthTokens` on Web and a secret-free `AndroidAuth` view on Android; mutable identity semantics end. | C9 | API + behavior | None | After its own stable notice release and interval | **Not met.** Update public typing/baselines and supersede ADR-0016's auth-instance rule at the cut. |
| C9-CRED-03 | Android `get_account_authuser()` becomes unsupported; account email comes from the master-token identity. | C9 | Behavior | None | After its own stable notice release and interval | **Not met.** Behavioral runway and both-backend identity tests; API allowance only if the audited signature changes. |
| C9-CRED-04 | `refresh_auth()` becomes side-effect-only (`None`) and Android no longer refreshes a Web sidecar. | C9 | API + behavior | None | After its own stable notice release and interval | **Not met.** Registered return-contract warning, public signature/baseline update, and behavior tests. |
| C9-CRED-05 | `from_storage()` selects its loader before acquisition; Android ignores inline Web auth and requires no cookie file/homepage request. | C9 | Behavior | None | After its own stable notice release and interval | **Not met.** Backend/path/profile/inline-env matrix in the behavioral runway. The home-root removal remains separately tracked as P8-30. |

## Existing P8/v1 registry: complete 34-row inventory

Guardrail abbreviations used in the table:

- **API**: exact `scripts/api-compat-allowlist.json` entry for each reported break, retained through
  release and checked with `audit_public_api_compat.py --check-stale`.
- **REG**: registered `_deprecation.DEPRECATION_SPECS` warning and
  `scripts/check_deprecation_targets.py`.
- **DOC**: exact first-cell docs runway verified by the v1 release gate.
- **BEH**: v1 behavioral-runway entry and focused behavior tests; no API allowance when the audit
  reports no structural break.

| ID | Exact v1 registry key and transition | Owner | Class | Runway | First shipped notice | Earliest eligible | C9b release gate / guardrail |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P8-01 | `client_legacy_constructor_options` — remove flat client tuning keywords | P5/C9 | API | REG | None (`0.9.0` is source-only) | Conditional v1.0.0 after stable v0.9.0 | **Not met**; API + REG |
| P8-02 | `client_legacy_from_storage_options` — remove flat stored-client tuning keywords | P5/C9 | API | REG | None (`0.9.0` is source-only) | Conditional v1.0.0 after stable v0.9.0 | **Not met**; API + REG |
| P8-03 | `client_rpc_call_web` — remove Web root `rpc_call()` | P7/C9 | API | REG | None (`0.9.0` is source-only) | Conditional v1.0.0 after stable v0.9.0 | **Not met**; API + REG |
| P8-04 | `client_rpc_call_android` — remove Android-to-Web root `rpc_call()` | P7/C9 | API + behavior | REG | None (`0.9.0` is source-only) | Conditional v1.0.0 after stable v0.9.0 | **Not met**; API + REG |
| P8-05 | `artifact_poll_follower_options` — make polling options per waiter | P6/C9 | Behavior | REG | None (`0.9.0` is source-only) | Conditional v1.0.0 after stable v0.9.0 | **Not met**; REG + BEH |
| P8-06 | `artifact_poll_follower_callback` — deliver every observed status to followers | P6/C9 | Behavior | REG | None (`0.9.0` is source-only) | Conditional v1.0.0 after stable v0.9.0 | **Not met**; REG + BEH |
| P8-07 | `` `NotebookLMClient.rpc_call(...)`::Remove Android LazyWebSidecar `` | P7/C9 | Behavior/internal graph | `LazyWebSidecar` compatibility marker, dependent on P8-04 notice | None | Conditional v1.0.0 after stable v0.9.0 | **Not met**; BEH and clean-import isolation; no stale API allowance for the private class |
| P8-08 | `auth_tokens_from_storage` — remove `AuthTokens.from_storage()` | Auth/C9 | API | REG | v0.8.1 | v1.0.0 | **Notice met**; API + REG |
| P8-09 | `auth_tokens_sync_storage_construction` — remove synchronous storage fallback | Auth/C9 | Behavior | REG | v0.8.1 | v1.0.0 | **Notice met**; REG + BEH only |
| P8-10 | `auth_tokens_flat_cookies` — remove `AuthTokens.flat_cookies` | Auth/C9 | API | REG | v0.8.1 | v1.0.0 | **Notice met**; API + REG |
| P8-11 | `auth_tokens_replace_cookie_jar` — remove `replace_cookie_jar()` | Auth/C9 | API | REG | None (`0.9.0` is source-only) | Conditional v1.0.0 after stable v0.9.0 | **Not met**; API + REG |
| P8-12 | `` `AuthTokens.cookies` / `AuthTokens.cookie_jar`::Remove AuthTokens.cookies `` | Auth/C9 | API field | DOC | v0.8.1 | v1.0.0 | **Notice met**; API + DOC |
| P8-13 | `` `AuthTokens.cookies` / `AuthTokens.cookie_jar`::Remove AuthTokens.cookie_jar `` | Auth/C9 | API field | DOC | v0.8.1 | v1.0.0 | **Notice met**; API + DOC |
| P8-14 | `` `AuthTokens.cookies` / `AuthTokens.cookie_jar`::Change AuthTokens class shape `` | Auth/C9 | API signature | DOC | v0.8.1 | v1.0.0 | **Notice met**; separate class-signature API allowance + DOC |
| P8-15 | `` `AuthTokens.cookie_snapshot`::Remove AuthTokens.cookie_snapshot `` | Auth/C9 | API field | DOC | None (`0.9.0` is source-only) | Conditional v1.0.0 after stable v0.9.0 | **Not met**; API + DOC |
| P8-16 | `` `AuthTokens.jar`::Remove AuthTokens.jar `` | Auth/C9 | API property | DOC | v0.8.1 | v1.0.0 | **Notice met**; API + DOC |
| P8-17 | `` `AuthTokens.cookie_header`::Remove AuthTokens.cookie_header `` | Auth/C9 | API property | DOC | v0.8.1 | v1.0.0 | **Notice met**; API + DOC |
| P8-18 | `` `AuthTokens.cookie_header_for(url)`::Remove AuthTokens.cookie_header_for `` | Auth/C9 | API method | DOC | v0.8.1 | v1.0.0 | **Notice met**; API + DOC |
| P8-19 | `artifact_from_api_response` — remove `Artifact.from_api_response()` | Types/C9 | API | REG | None (`0.9.0` is source-only) | Conditional v1.0.0 after stable v0.9.0 | **Not met**; API + REG |
| P8-20 | `artifact_from_mind_map` — remove `Artifact.from_mind_map()` | Types/C9 | API | REG | None (`0.9.0` is source-only) | Conditional v1.0.0 after stable v0.9.0 | **Not met**; API + REG |
| P8-21 | `collection_from_api_response` — remove `Collection.from_api_response()` | Types/C9 | API | REG | None (`0.9.0` is source-only) | Conditional v1.0.0 after stable v0.9.0 | **Not met**; API + REG |
| P8-22 | `label_from_api_response` — remove `Label.from_api_response()` | Types/C9 | API | REG | None (`0.9.0` is source-only) | Conditional v1.0.0 after stable v0.9.0 | **Not met**; API + REG |
| P8-23 | `notebook_from_api_response` — remove `Notebook.from_api_response()` | Types/C9 | API | REG | None (`0.9.0` is source-only) | Conditional v1.0.0 after stable v0.9.0 | **Not met**; API + REG |
| P8-24 | `share_status_from_api_response` — remove `ShareStatus.from_api_response()` | Types/C9 | API | REG | None (`0.9.0` is source-only) | Conditional v1.0.0 after stable v0.9.0 | **Not met**; API + REG |
| P8-25 | `shared_user_from_api_response` — remove `SharedUser.from_api_response()` | Types/C9 | API | REG | None (`0.9.0` is source-only) | Conditional v1.0.0 after stable v0.9.0 | **Not met**; API + REG |
| P8-26 | `source_from_api_response` — remove `Source.from_api_response()` | Types/C9 | API | REG | None (`0.9.0` is source-only) | Conditional v1.0.0 after stable v0.9.0 | **Not met**; API + REG |
| P8-27 | `source_from_row` — remove `Source.from_row()` | Types/C9 | API | REG | None (`0.9.0` is source-only) | Conditional v1.0.0 after stable v0.9.0 | **Not met**; API + REG |
| P8-28 | `mcp_confirmed_name_references` — reject names/partial IDs on confirmed mutations | P7/C9 | Behavior | REG | None (`0.9.0` is source-only) | Conditional v1.0.0 after stable v0.9.0 | **Not met**; REG + BEH |
| P8-29 | `` Awaiting `NotebookLMClient.from_storage(...)`::Remove awaitable factory path `` | Client/C9 | Behavior | Inline gated warning | v0.5.0 | v1.0.0 | **Notice met**; BEH only; the private wrapper produces no API-audit break |
| P8-30 | `Pre-profiles home-root layout::Remove home-root credential fallback` | Paths/C9 | Behavior | Inline gated warning | v0.8.1 | v1.0.0 | **Notice met**; BEH only; no API allowance |
| P8-31 | `` `ChatReference.answer_start_char` / `answer_end_char` (dataclass fields)::Remove answer_start_char `` | Types/C9 | API field | DOC | v0.8.1 | v1.0.0 | **Notice met**; API + DOC |
| P8-32 | `` `ChatReference.answer_start_char` / `answer_end_char` (dataclass fields)::Remove answer_end_char `` | Types/C9 | API field | DOC | v0.8.1 | v1.0.0 | **Notice met**; API + DOC |
| P8-33 | `` `Notebook.modified_at` (dataclass field)::Remove Notebook.modified_at `` | Types/C9 | API field | DOC | v0.8.1 | v1.0.0 | **Notice met**; API + DOC |
| P8-34 | `` `NotebookMetadata.modified_at` (property)::Remove NotebookMetadata.modified_at `` | Types/C9 | API property | Inline gated warning + docs | v0.8.1 | v1.0.0 | **Notice met**; API + BEH |

The P8 API allowance must also cover every removed constructor/from-storage keyword and every
public compatibility export that the audit actually reports. Conversely, P8-07, P8-09, P8-29, and
P8-30 are behavioral/private shapes and must not receive invented allowances: `--check-stale`
rejects entries with no matching `ApiBreak`. The v0.8.0 release-gate pins remain historical and
must not be repopulated.

## Independent C3/C4/C5 migration rows

These migrations were designed after the original P8 inventory. None has a shipped notice at the
audit baseline, so none is authorized merely because a v1 release occurs. Implementing phases must
replace “pending exact key” with the literal registry key and first shipped version.

| ID | Transition | Owner | Class | First shipped notice | Earliest eligible | Gate and disposition |
| --- | --- | --- | --- | --- | --- | --- |
| C3-01 | Legacy artifact `get()`/`get_or_none()` no-hit behavior changes from best-effort aggregate absence to authoritative `MISSING`/`UNKNOWN`. | C3 | Behavior; signatures remain unchanged | None; source registers `artifact_ambiguous_absence` for the next stable release | After that warning ships and its required interval | `artifact_ambiguous_absence` fires only when incomplete backing would become false absence; additive `list_with_status()`/`lookup()` and the both-backend completeness matrix are present. Do not count the source registration as shipped. |
| C3-02 | Android `get_prompt(..., require_complete=False)` default becomes strict/authoritative. | C3 | API default + behavior | None; source registers `artifact_ambiguous_absence` for the next stable release | After that warning ships and its required interval | The additive `require_complete=True` path is strict now and first-party prompt consumers select it. The default remains `False`; the ambiguous legacy path emits the registered warning. Web's direct decoder remains strict without a redundant lookup. An exact changed-default API allowance is required at the eventual cut. |
| C4-01 | Omitted Web request settings change from live environment resolution to construction-bound defaults. | C4 | Behavior | None | After its own stable preview/warning release and interval | Explicit `WebRequestOptions` is additive and first-party factories opt in. No Python default flip or runtime deprecation warning ships in this change. Record an actual stable notice tag and interval before the later default switch; retain dynamic mode through v1 if ineligible. Deferred-open, refresh, and environment-mutation tests preserve both modes. |
| C5A-01 | Interactive waited mind-map terminal policy default changes from legacy hydration after failure to raising `ArtifactNotReadyError`. | C5a | API default + behavior | None | After its own stable warning release and interval | Warn only when the legacy path continues after an unsuccessful terminal state; exact changed-default allowance at the cut. |
| C5A-02 | A formerly ignored generation option becomes rejected. No concrete option is approved at this baseline. | C5a | Behavior, possibly API default | None | Per-option; after that option's own stable notice and interval | Create one ledger/registry row per concrete option. This placeholder cannot authorize any rejection. |
| C5B-01 | Remove raw download-prefetch keywords from nine public download methods: `artifacts_data`, `artifacts`, and `mind_maps` as applicable. | C5b | API signatures | None; source registers `artifact_raw_download_prefetch` for the next stable release | After a stable signature warning release and interval, if retirement is retained | One exact API allowance per removed method/keyword break; first-party callers use typed preparation/download. Registered warning: `artifact_raw_download_prefetch` (source planned for 0.9.0; no shipped evidence). Retain until its own interval is met. |

## C9b gate result at this audit

The source implementation prerequisite P4–P7 is present: integrated ownership work commit
`70f0eb44a` is an ancestor of the audited baseline. ADR-0039 now makes the credential destination
reviewable. The release cut is still **not eligible**:

- **Met notice evidence:** P8-08 through P8-10, P8-12 through P8-14, P8-16 through P8-18, and
  P8-29 through P8-34. These shipped in v0.8.1 or earlier and target the next major.
- **Unmet notice evidence:** P8-01 through P8-07, P8-11, P8-15, and P8-19 through P8-28. All rely
  on a stable v0.9.0 that does not exist.
- **Unmet credential migration evidence:** C9-CRED-01 through C9-CRED-05 have no shipped warnings.
- **Unmet later migration evidence:** every C3/C4/C5 row above has no shipped warning; those paths
  must survive v1 if their gates have not matured.
- **Still required at the actual cut:** exact API-break audit and non-stale allowances, drainage of
  the complete v1 registry, deprecation-target validation, migration documentation, clean-process
  Web/Android import isolation, backend/path/profile/env precedence tests, credential mismatch
  before I/O, and the protected release workflow in [releasing.md](releasing.md).

Re-run the remote release/tag/source audit immediately before scheduling C9b. This page records the
2026-09-06 result; it is evidence, not a permanent prediction about future releases.
