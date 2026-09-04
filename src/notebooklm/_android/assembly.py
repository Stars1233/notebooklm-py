"""Branch-local composition for the Android backend."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from .._client_contracts import BackendAssembly, installed_backend_map
from .._runtime.config import resolve_chat_read_timeout
from .artifacts import AndroidArtifactsAPI
from .assets import AndroidAssetDownloadService
from .auth import _make_bearer_provider
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
    from ..auth import AuthTokens
    from ..client import NotebookLMClient


def assemble_android_backend(
    client: NotebookLMClient,
    *,
    auth: AuthTokens,
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
    shared: Any,
) -> BackendAssembly:
    """Install only the Android graph and return its neutral lifecycle parts."""

    bearer_provider = _make_bearer_provider(
        Path(auth.storage_path) if auth.storage_path is not None else None
    )
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
