# Artifact download contracts

`notebooklm.downloads` owns the canonical representation registry below the
application layer. Backend preparation and adapter filename/content-type policy
use the same definitions. `_app.download_specs` retains its existing imports as
compatibility reexports. This move is required by C5b so backend code can consume
the registry without depending on application orchestration.

Supported metadata imports are `DOWNLOAD_REGISTRY`, `DOWNLOAD_SPECS_BY_NAME`,
`DOWNLOAD_FORMAT_NAMES`, `EXTENSION_MIME_TYPES`, `FORMAT_EXTENSIONS`,
`DownloadFormatSpec`, `DownloadRegistryEntry`, `DownloadTypeSpec`, and
`resolve_download_format` from `notebooklm.downloads`. They describe implemented
representations, not account entitlement or a promise of upstream availability.
Audio uses `.m4a` with `audio/mp4`; choosing another representation changes its
extension and MIME type together. Unsupported formats raise `ValidationError`.

`ArtifactDownloadRequest` and `ArtifactDownloadSelection` are public frozen
values imported from `notebooklm.types`. A request identifies the notebook,
artifact kind, and optional output format. Omitting the format selects the
existing per-kind default. A prepared selection contains artifact identity,
title, creation time, representation, extension, and MIME type for application
selection and naming. Its identity belongs to one backend instance and client
generation; copying its visible fields does not transfer download authority.

The private `PreparedDownloadCache` holds backend-specific snapshots in a weak
identity map. A selection never contains raw rows, protobufs, cookies, or signed
URLs. Releasing the public selection releases its cached snapshot; the next
operation in a different generation invalidates retained old snapshots. Backend
entry points must obtain the actual operation lease before consulting the cache,
so the epoch is not a caller-supplied capability. Admission and transfer owners
remain responsible for graceful close, cancellation, and publication fences.


## Prepare and download

```python
from notebooklm.types import ArtifactDownloadRequest, ArtifactType

listing = await client.artifacts.prepare_downloads(
    ArtifactDownloadRequest(notebook_id, ArtifactType.AUDIO)
)
selection = next(item for item in listing.selections if item.artifact_id == artifact_id)
await client.artifacts.download(selection, "overview.m4a")
```

`ArtifactDownloadListing` carries `selections`, `is_complete`, and bounded,
sanitized component failures. A positive exact match remains usable when the
secondary mind-map listing is unavailable. An incomplete listing cannot prove
absence, the newest item, or that an all-items download is exhaustive. The
application action rejects these uncertain selections before creating files.

Preparation reads each required listing component once and keeps protocol data
inside its backend. Download consumes the same selection object under an admitted
operation scope. Android retains its native ownership verification and necessary
note hydration; equivalent results do not imply identical Web and Android RPC
counts. Client close/reopen invalidates earlier selections.

The nine existing per-kind methods retain their signatures and defaults and
now delegate through preparation and typed download. Default mind-map selection
retains note-backed priority; Android retains its last-modified ordering. Raw
prefetch keywords remain accepted by compatibility adapters and emit the
registered `artifact_raw_download_prefetch` warning only when supplied. The new
typed path emits no such warning. Retirement requires this warning's own shipped
compatibility interval; a planned release date does not establish eligibility.
