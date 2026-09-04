"""Shared artifact selectors for live E2E tests and their unit coverage."""

from __future__ import annotations

from notebooklm import Artifact

URL_BACKED_ARTIFACT_FAMILIES = frozenset({"audio", "video", "infographic", "slide_deck"})
URL_BACKED_STUDIO_TYPES = frozenset(
    family.replace("_", "-") for family in URL_BACKED_ARTIFACT_FAMILIES
)


def completed_url_artifacts(artifacts: list[Artifact], family: str) -> list[Artifact]:
    """Return completed artifacts whose listing exposes the required asset URL."""

    if family not in URL_BACKED_ARTIFACT_FAMILIES:
        raise ValueError(f"artifact family is not URL-backed: {family}")
    return [
        artifact
        for artifact in artifacts
        if artifact.kind == family and artifact.is_completed and bool(artifact.url)
    ]


def studio_item_has_download_payload(item: dict[str, object]) -> bool:
    """Check the URL field for Studio types whose download requires one."""

    return item.get("type") not in URL_BACKED_STUDIO_TYPES or bool(item.get("url"))


def completed_interactive_mind_maps(artifacts: list[Artifact]) -> list[Artifact]:
    """Return only downloadable interactive mind-map artifacts."""
    return [
        artifact
        for artifact in artifacts
        if artifact.is_interactive_mind_map and artifact.is_completed
    ]
