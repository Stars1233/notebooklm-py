"""Backend-level contracts for opaque prepared artifact downloads."""

from __future__ import annotations

import warnings
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest

from notebooklm._types.artifact_download import ArtifactDownloadRequest
from notebooklm._web.artifacts import WebArtifactsAPI
from notebooklm._web.mind_maps import NoteBackedMindMapService
from notebooklm._web.notes import NoteService
from notebooklm.exceptions import RPCError, ValidationError
from notebooklm.types import ArtifactListingComponent, ArtifactType, MindMap, MindMapKind
from tests._fixtures.fake_core import make_fake_core
from tests.unit.android.test_artifacts import (
    _PROTO,
    LIST_ARTIFACTS_METHOD,
    _artifact,
    _graph,
)

_INTERACTIVE_MIND_MAP_ROW = [
    "interactive",
    "Studio map",
    4,
    None,
    3,
    None,
    None,
    None,
    None,
    [None, [4]],
]


def _web_api(
    studio_rows: list[object], *, note_result: list[object] | BaseException
) -> WebArtifactsAPI:
    core = make_fake_core(rpc_call=AsyncMock(return_value=studio_rows))
    mind_maps = MagicMock(spec=NoteBackedMindMapService)
    mind_maps.list_mind_maps = (
        AsyncMock(side_effect=note_result)
        if isinstance(note_result, BaseException)
        else AsyncMock(return_value=note_result)
    )
    notebooks = MagicMock()
    notebooks.get_source_ids = AsyncMock(return_value=[])
    return WebArtifactsAPI(
        rpc=core,
        supervisor=core,
        notebooks=notebooks,
        mind_maps=mind_maps,
        note_service=MagicMock(spec=NoteService),
    )


@pytest.mark.asyncio
async def test_web_prepared_interactive_mind_map_survives_notes_outage_without_retry() -> None:
    """A positive Studio hit remains executable despite a secondary outage."""
    api = _web_api([_INTERACTIVE_MIND_MAP_ROW], note_result=RPCError("temporary"))
    api._download_mind_map_legacy = AsyncMock(return_value="map.json")  # type: ignore[method-assign]

    listing = await api.prepare_downloads(ArtifactDownloadRequest("nb", ArtifactType.MIND_MAP))

    assert [selection.artifact_id for selection in listing.selections] == ["interactive"]
    assert not listing.is_complete
    assert listing.failures[0].component is ArtifactListingComponent.NOTE_BACKED_MIND_MAPS
    assert await api.download(listing.selections[0], "map.json") == "map.json"
    api._mind_maps.list_mind_maps.assert_awaited_once_with("nb")
    api._download_mind_map_legacy.assert_awaited_once_with(
        "nb",
        "map.json",
        "interactive",
        mind_maps=[],
        artifacts_data=[_INTERACTIVE_MIND_MAP_ROW],
    )


@pytest.mark.asyncio
async def test_android_prepared_audio_retains_exact_ownership_read_and_format() -> None:
    raw = _artifact("audio", type_code=_PROTO.ARTIFACT_TYPE_AUDIO_OVERVIEW)
    raw.audio_overview.media_urls.add(
        url="https://lh3.googleusercontent.com/audio.m4a",
        type=_PROTO.MEDIA_STREAMING_TYPE_DOWNLOAD,
    )
    session, _, _, assets, api = _graph([raw])

    listing = await api.prepare_downloads(ArtifactDownloadRequest("notebook-1", ArtifactType.AUDIO))

    selection = listing.selections[0]
    assert (selection.representation, selection.extension, selection.mime_type) == (
        "m4a",
        ".m4a",
        "audio/mp4",
    )
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        assert await api.download(selection, "audio.m4a") == "audio.m4a"
    assert not [warning for warning in captured if warning.category is DeprecationWarning]
    assert [call[0] for call in session.calls] == [
        LIST_ARTIFACTS_METHOD,
        # Selection reuses its aggregate snapshot; native exact-id ownership
        # remains a separate required read before transfer.
        LIST_ARTIFACTS_METHOD,
    ]
    assert assets.representation_calls == [
        ("https://lh3.googleusercontent.com/audio.m4a", "audio.m4a", "audio")
    ]


@pytest.mark.asyncio
async def test_android_prepared_note_backed_map_reuses_its_hydrated_tree(tmp_path) -> None:
    session, _, mind_maps, _, api = _graph()
    mind_maps.mind_maps = [
        MindMap(
            id="note-map",
            notebook_id="notebook-1",
            title="Note map",
            kind=MindMapKind.NOTE_BACKED,
            tree={"name": "Root", "children": []},
        )
    ]
    output = tmp_path / "note-map.json"

    listing = await api.prepare_downloads(
        ArtifactDownloadRequest("notebook-1", ArtifactType.MIND_MAP)
    )

    assert [selection.artifact_id for selection in listing.selections] == ["note-map"]
    assert mind_maps.calls == ["notebook-1"]
    assert await api.download(listing.selections[0], str(output)) == str(output)
    assert '"name": "Root"' in output.read_text()
    assert mind_maps.calls == ["notebook-1"]
    assert [call[0] for call in session.calls] == [LIST_ARTIFACTS_METHOD]


@pytest.mark.asyncio
async def test_prepared_selection_rejects_a_second_backend_and_forged_identity() -> None:
    raw = _artifact("audio", type_code=_PROTO.ARTIFACT_TYPE_AUDIO_OVERVIEW)
    raw.audio_overview.media_urls.add(
        url="https://lh3.googleusercontent.com/audio.m4a",
        type=_PROTO.MEDIA_STREAMING_TYPE_DOWNLOAD,
    )
    _, _, _, _, owner = _graph([raw])
    _, _, _, _, other = _graph([raw])
    selection = (
        await owner.prepare_downloads(ArtifactDownloadRequest("notebook-1", ArtifactType.AUDIO))
    ).selections[0]

    with pytest.raises(ValidationError):
        await other.download(selection, "audio.m4a")
    with pytest.raises(ValidationError):
        await owner.download(replace(selection, artifact_id="forged"), "audio.m4a")


@pytest.mark.asyncio
async def test_prepare_rejects_unsupported_representation_before_android_listing() -> None:
    session, _, _, _, api = _graph()

    with pytest.raises(ValidationError, match="Unsupported download format"):
        await api.prepare_downloads(
            ArtifactDownloadRequest("notebook-1", ArtifactType.AUDIO, "mp3")
        )

    assert session.calls == []


@pytest.mark.asyncio
async def test_legacy_raw_prefetch_remains_supported_with_its_targeted_warning() -> None:
    raw = _artifact("audio", type_code=_PROTO.ARTIFACT_TYPE_AUDIO_OVERVIEW)
    raw.audio_overview.media_urls.add(
        url="https://lh3.googleusercontent.com/audio.m4a",
        type=_PROTO.MEDIA_STREAMING_TYPE_DOWNLOAD,
    )
    _, _, _, _, api = _graph([raw])

    with pytest.warns(DeprecationWarning, match="Raw artifact download prefetch"):
        assert (
            await api.download_audio("notebook-1", "audio.m4a", artifacts_data=[raw]) == "audio.m4a"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "legacy_name", "output_format"),
    [
        (ArtifactType.AUDIO, "_download_audio_legacy", None),
        (ArtifactType.VIDEO, "_download_video_legacy", None),
        (ArtifactType.INFOGRAPHIC, "_download_infographic_legacy", None),
        (ArtifactType.SLIDE_DECK, "_download_slide_deck_legacy", "pptx"),
        (ArtifactType.REPORT, "_download_report_legacy", None),
        (ArtifactType.MIND_MAP, "_download_mind_map_legacy", None),
        (ArtifactType.DATA_TABLE, "_download_data_table_legacy", None),
        (ArtifactType.QUIZ, "_download_quiz_legacy", "markdown"),
        (ArtifactType.FLASHCARDS, "_download_flashcards_legacy", "html"),
    ],
)
async def test_web_legacy_prefetch_dispatch_covers_every_supported_kind(
    kind: ArtifactType,
    legacy_name: str,
    output_format: str | None,
) -> None:
    """The backend dispatch is closed and does not reflect over public method names."""
    api = _web_api([], note_result=[])
    legacy = AsyncMock(return_value="out")
    setattr(api, legacy_name, legacy)

    assert (
        await api._download_with_legacy_prefetch(
            ArtifactDownloadRequest("nb", kind, output_format),
            "out",
            "artifact",
            artifacts_data=["raw"],
            mind_maps=["note"],
            artifacts=[],
        )
        == "out"
    )
    assert legacy.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "legacy_name"),
    [
        (ArtifactType.SLIDE_DECK, "_download_slide_deck_legacy"),
        (ArtifactType.QUIZ, "_download_quiz_legacy"),
        (ArtifactType.FLASHCARDS, "_download_flashcards_legacy"),
    ],
)
async def test_web_legacy_prefetch_keeps_an_explicit_empty_representation(
    kind: ArtifactType, legacy_name: str
) -> None:
    """An explicit empty value reaches the legacy validator unchanged."""
    api = _web_api([], note_result=[])
    legacy = AsyncMock(return_value="out")
    setattr(api, legacy_name, legacy)

    await api._download_with_legacy_prefetch(
        ArtifactDownloadRequest("nb", kind, ""), "out", "artifact"
    )

    assert legacy.await_args.args[3] == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "legacy_name"),
    [
        (ArtifactType.SLIDE_DECK, "_download_slide_deck_legacy"),
        (ArtifactType.QUIZ, "_download_quiz_legacy"),
        (ArtifactType.FLASHCARDS, "_download_flashcards_legacy"),
    ],
)
async def test_android_legacy_prefetch_keeps_an_explicit_empty_representation(
    kind: ArtifactType, legacy_name: str
) -> None:
    """An explicit empty value reaches the native legacy validator unchanged."""
    _, _, _, _, api = _graph()
    legacy = AsyncMock(return_value="out")
    setattr(api, legacy_name, legacy)

    await api._download_with_legacy_prefetch(
        ArtifactDownloadRequest("notebook-1", kind, ""), "out", "artifact"
    )

    assert legacy.await_args.args[3] == ""
