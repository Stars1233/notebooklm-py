"""Shared artifact selectors for live E2E tests and their unit coverage."""

from __future__ import annotations

from notebooklm import Artifact

URL_BACKED_ARTIFACT_FAMILIES = frozenset({"audio", "video", "infographic", "slide_deck"})
URL_BACKED_STUDIO_TYPES = frozenset(
    family.replace("_", "-") for family in URL_BACKED_ARTIFACT_FAMILIES
)


def completed_download_candidates(
    artifacts: list[Artifact], family: str, *, backend: str
) -> list[Artifact]:
    """Return completed artifacts whose backend can attempt payload resolution."""

    if family not in URL_BACKED_ARTIFACT_FAMILIES:
        raise ValueError(f"artifact family is not URL-backed: {family}")
    hydrate_android_slide = backend == "android" and family == "slide_deck"
    candidates = [
        artifact
        for artifact in artifacts
        if not bool(getattr(artifact, "is_unclassified_type4", False))
        and artifact.kind == family
        and artifact.is_completed
        and (hydrate_android_slide or bool(artifact.url))
    ]
    return sorted(candidates, key=lambda artifact: bool(artifact.url), reverse=True)


def studio_item_may_have_download_payload(item: dict[str, object], *, backend: str) -> bool:
    """Check whether the selected backend can attempt Studio payload resolution."""

    item_type = item.get("type")
    hydrate_android_slide = backend == "android" and item_type == "slide-deck"
    return (
        item_type not in URL_BACKED_STUDIO_TYPES or hydrate_android_slide or bool(item.get("url"))
    )


def completed_interactive_mind_maps(artifacts: list[Artifact]) -> list[Artifact]:
    """Return only downloadable interactive mind-map artifacts."""
    return [
        artifact
        for artifact in artifacts
        if artifact.is_interactive_mind_map and artifact.is_completed
    ]
