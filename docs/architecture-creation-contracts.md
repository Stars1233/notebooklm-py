# Artifact creation contracts

The shared `ArtifactsAPI` resolves source selection and language, then passes a
per-family input request to `_artifact/creation_policy.py`. That owner validates
compatible combinations and resolves all defaults into the frozen per-family
union in `_artifact/creation_normalized.py`. Each family has explicit fields;
there is no family string, arbitrary options mapping, or raw request wrapper at
`_send_create_artifact`.

The Web encoder in `_web/params/creation.py` and Android encoder in
`_android/artifact_creation.py` exhaustively dispatch that union and only encode
protocol fields. The hooks retain transport, journal, and response validation.
The old private Web payload builders remain compatibility entry points and use
the same shared normalization owner. Their historical acceptance of preset-style
prompts is explicit in `WEB_BUILDER_POLICY`; public video methods continue to
reject that unsupported combination.

Numeric selections in the normalized types are resolved domain enum values. This
preserves Web's historical acceptance of enum-like values without claiming that
an arbitrary options bag is typed. Android checks membership in the expected enum;
quiz and flashcard quantity/difficulty are checked on both backends. Report
prompts and client defaults have one shared owner.

| Input or capability | Web | Android |
| --- | --- | --- |
| Omitted sources | Resolve notebook sources | Resolve notebook sources |
| Explicit empty sources | Send the explicit empty selection | Reject before creation dispatch |
| Empty language or non-string instructions | Preserve existing permissive behavior where previously accepted | Reject before creation dispatch |
| Concept explanation report | Unsupported | Supported |
| Interactive mind-map instructions | Whitespace-only prompt omitted; nonblank text preserved | Text preserved |
| Interactive mind-map language | Accepted but not encoded | Encoded |

`creation_capabilities` is immutable implementation metadata. It does not probe
account entitlement and does not authorize newly rejecting an accepted option.
A later rejection needs its own concrete migration entry and notice interval.

## Mind-map migration notice

`mind_maps.generate(..., failure_policy="raise")` is an additive opt-in. For a
waited interactive map, failed or removed completion raises `ArtifactNotReadyError`
before fetching the tree. Completed maps hydrate normally; a timeout propagates.
Non-waited interactive generation and synchronous note-backed generation retain
their existing behavior. First-party generation orchestration selects `"raise"`.

The Python default remains `"legacy"`. Web emits the registered
`mind_map_legacy_terminal_hydration` `DeprecationWarning` only when it actually
continues hydration after failed/removed completion. Android already raises in
legacy mode and does not emit this warning. The normal deprecation suppression
gate applies.

Source registration is not a shipped notice. C5A-01 in the
[release migration ledger](release-migration-ledger.md) records **first shipped
notice: None**. The v1.0 target is conditional on this warning's own stable release
and migration interval; otherwise the default survives until a later breaking
release. It does not borrow another deprecation's notice date.

`tests/unit/test_creation_conformance.py` exercises the real artifact facades,
normalized hook values, protocol terminals, compatibility differences, both
concrete mind-map facades, and first-party strict orchestration.
