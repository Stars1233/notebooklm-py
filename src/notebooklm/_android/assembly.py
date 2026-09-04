"""Branch-local composition for the Android backend."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from .._auth.mint_service import MintService
from .._auth.profile_store import ProfileStore
from .._client_contracts import BackendAssembly, installed_backend_map
from .._runtime.config import normalize_max_concurrent_uploads, resolve_chat_read_timeout
from .._runtime.init import SharedRuntimeConfig, build_collaborators
from .artifacts import AndroidArtifactsAPI
from .assets import AndroidAssetDownloadService
from .auth import MasterTokenReader, OAuthMinter, _make_bearer_provider, _NoMasterTokenReader
from .chat import AndroidChatAPI
from .collections import AndroidCollectionsAPI
from .labels import AndroidLabelsAPI
from .mind_maps import AndroidMindMapsAPI
from .note_backed import NoteBackedMindMapArtifactAdapter
from .notebooks import AndroidNotebooksAPI
from .notes import AndroidNotesAPI
from .phenotype import PhenotypeTokenProvider
from .raw import AndroidRawAPI
from .research import AndroidResearchAPI
from .runtime import AndroidRuntime
from .session import AndroidSession
from .settings import AndroidSettingsAPI
from .sharing import AndroidSharingAPI
from .sources import AndroidSourcesAPI
from .upload import AndroidUploadPipeline

if TYPE_CHECKING:
    from ..client import NotebookLMClient
    from ..types import RpcTelemetryEvent


def _validate_android_settings(
    *,
    rate_limit_max_retries: int,
    server_error_max_retries: int,
    max_concurrent_uploads: int | None,
) -> None:
    """Validate Android-owned values in the historical constructor order."""

    if rate_limit_max_retries < 0:
        raise ValueError(f"rate_limit_max_retries must be >= 0, got {rate_limit_max_retries}")
    if server_error_max_retries < 0:
        raise ValueError(f"server_error_max_retries must be >= 0, got {server_error_max_retries}")
    normalize_max_concurrent_uploads(max_concurrent_uploads)


def assemble_android_backend(
    client: NotebookLMClient,
    *,
    profile_path: Path | None,
    master_token_reader: MasterTokenReader | None,
    oauth_minter: OAuthMinter | None,
    timeout: float,
    refresh_retry_delay: float,
    rate_limit_max_retries: int,
    server_error_max_retries: int,
    max_concurrent_uploads: int | None,
    upload_timeout: httpx.Timeout | None,
    chat_timeout: float | None,
    import_research_timeout: float | None,
    chat_response_max_bytes: int | None,
    sleep: Callable[[float], Awaitable[Any]] | None,
    shared_config: SharedRuntimeConfig,
    on_rpc_event: Callable[[RpcTelemetryEvent], object] | None,
) -> BackendAssembly:
    """Install only the Android graph and return its neutral lifecycle parts."""

    _validate_android_settings(
        rate_limit_max_retries=rate_limit_max_retries,
        server_error_max_retries=server_error_max_retries,
        max_concurrent_uploads=max_concurrent_uploads,
    )
    shared = build_collaborators(shared_config, on_rpc_event=on_rpc_event)
    if master_token_reader is None:
        master_token_reader = (
            ProfileStore(profile_path) if profile_path is not None else _NoMasterTokenReader()
        )
    if oauth_minter is None:
        oauth_minter = MintService()
    bearer_provider = _make_bearer_provider(master_token_reader, oauth_minter)
    session = AndroidSession(
        bearer_provider,
        shared.call_supervisor,
        timeout=timeout,
        rate_limit_max_retries=rate_limit_max_retries,
        server_error_max_retries=server_error_max_retries,
        refresh_retry_delay=refresh_retry_delay,
        metrics=shared.metrics,
        sleep=sleep,
    )
    asset_downloads = AndroidAssetDownloadService(
        bearer_provider=bearer_provider,
        supervisor=shared.call_supervisor,
    )
    upload_pipeline = AndroidUploadPipeline(
        session=session,
        bearer_provider=bearer_provider,
        upload_timeout=upload_timeout,
        max_concurrent_uploads=max_concurrent_uploads,
        record_upload_queue_wait=shared.metrics.record_upload_queue_wait,
    )
    phenotype = PhenotypeTokenProvider()
    android = AndroidRuntime(
        bearer_provider=bearer_provider,
        session=session,
        upload_pipeline=upload_pipeline,
        asset_downloads=asset_downloads,
        phenotype=phenotype,
    )
    client._android_runtime = android
    client._web_runtime = None
    client._raw = AndroidRawAPI(session)

    client.sources = AndroidSourcesAPI(
        session,
        upload_pipeline,
        drive_download=upload_pipeline.drive_download_scope,
        phenotype=phenotype,
    )
    client.notebooks = AndroidNotebooksAPI(session, client.sources)
    client.notes = AndroidNotesAPI(session)
    note_backed_artifacts = NoteBackedMindMapArtifactAdapter(
        client.notes._list_note_backed_mind_maps,
    )
    client.artifacts = AndroidArtifactsAPI(
        session=session,
        supervisor=shared.call_supervisor,
        notebooks=client.notebooks,
        mind_maps=note_backed_artifacts,
        asset_downloads=asset_downloads,
    )
    client.mind_maps = AndroidMindMapsAPI(
        session=session,
        artifacts=client.artifacts,
        notes=client.notes,
    )
    client.chat = AndroidChatAPI(
        session=session,
        loop_guard=shared.call_supervisor,
        chat_timeout=resolve_chat_read_timeout(chat_timeout, timeout),
        chat_response_max_bytes=chat_response_max_bytes,
        notebooks=client.notebooks,
        created_chat_sessions=client.notebooks,
    )
    client.research = AndroidResearchAPI(
        session,
        client.sources,
        base_timeout=timeout,
        import_research_timeout=import_research_timeout,
    )
    client.settings = AndroidSettingsAPI(session)
    client.sharing = AndroidSharingAPI(session)
    client.labels = AndroidLabelsAPI(session, list_sources=client.sources.list)
    client.collections = AndroidCollectionsAPI(
        session,
        list_notebooks=client.notebooks.list,
    )

    return BackendAssembly(
        backend="android",
        runtime=android,
        collaborators=shared,
        transports=(session, asset_downloads, upload_pipeline, phenotype),
        loop_participants=(
            shared.call_supervisor,
            client.chat,
            bearer_provider,
            session,
            upload_pipeline,
        ),
        backends=installed_backend_map("android"),
    )


__all__ = ["assemble_android_backend"]
