"""P0 coupling measurements and shrink-only ratchet semantics."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.audit_backend_coupling import (
    BACKEND_STAGES,
    _scan_static_source,
    build_static_projection,
    runtime_projection_growth,
    static_projection_growth,
)

from tests._baselines.registry import baseline_by_name

pytestmark = pytest.mark.repo_lint


def _runtime_baseline() -> dict[str, object]:
    value = baseline_by_name("backend_runtime_coupling").load()
    assert isinstance(value, dict)
    return value


def _stage(backend: str, stage: str) -> dict[str, object]:
    backends = _runtime_baseline()["backends"]
    assert isinstance(backends, dict)
    backend_value = backends[backend]
    assert isinstance(backend_value, dict)
    stages = backend_value["stages"]
    assert isinstance(stages, dict)
    value = stages[stage]
    assert isinstance(value, dict)
    return value


def test_public_entries_are_distinct_probes_with_the_current_eager_delta() -> None:
    entries = _runtime_baseline()["public_entries"]
    assert isinstance(entries, dict)
    assert set(entries) == {
        "android_raw_api",
        "client_reexport",
        "legacy_client_attribute",
        "package",
        "raw_module",
        "web_raw_api",
    }
    deltas = {tuple(value["module_delta"]) for value in entries.values()}
    assert len(deltas) == 1
    (delta,) = deltas

    # This is the relative-import false negative the old ``__import__`` hook
    # missed: Python passed ``_android.runtime`` with ``level=1``.  The clean
    # sys.modules delta records the resolved module instead.
    assert "notebooklm._android.runtime" in delta
    assert "notebooklm._web.transport.init" in delta


def test_backend_stage_matrix_is_complete_and_records_every_dimension() -> None:
    backends = _runtime_baseline()["backends"]
    assert isinstance(backends, dict)
    assert set(backends) == set(BACKEND_STAGES)
    for backend, expected_stages in BACKEND_STAGES.items():
        backend_value = backends[backend]
        assert isinstance(backend_value, dict)
        stages = backend_value["stages"]
        assert isinstance(stages, dict)
        assert set(stages) == set(expected_stages)
        for stage in stages.values():
            assert set(stage) == {
                "backend_objects",
                "lifecycle",
                "module_counts",
                "module_delta",
                "network_destinations",
                "optional_android_module_delta",
                "profile_reads",
                "profile_writes",
            }


def test_current_android_homepage_compatibility_and_sidecar_boundary_are_explicit() -> None:
    built = _stage("android", "build_from_storage")
    assert built["network_destinations"] == {"GET https://notebook.google.com/": 1}
    assert built["profile_writes"] == {}

    constructed = _stage("android", "construct_direct")
    backend_objects = constructed["backend_objects"]
    assert isinstance(backend_objects, dict)
    assert {name for name in backend_objects if name.startswith("notebooklm._web")} == {
        "notebooklm._web.transport.seams.ClientSeams",
        "notebooklm._web.transport.sidecar.LazyWebSidecar",
    }
    lifecycle = constructed["lifecycle"]
    assert isinstance(lifecycle, dict)
    assert sum("LazyWebSidecar" in name for name in lifecycle["transports"]) == 1
    assert sum("LazyWebSidecar" in name for name in lifecycle["loop_participants"]) == 1

    typed = _stage("android", "typed_operation")
    assert typed["network_destinations"] == {
        "GET https://notebook.google.com/": 1,
        "GRPC notebooklm-pa.googleapis.com:443": 1,
    }
    compatible = _stage("android", "deprecated_rpc_call")
    assert compatible["network_destinations"] == {
        "GET https://notebook.google.com/": 1,
        "GRPC notebooklm-pa.googleapis.com:443": 1,
        "POST https://notebook.google.com/_/LabsTailwindUi/data/batchexecute": 1,
    }
    assert compatible["backend_objects"]["notebooklm._web.transport.init.WebRuntime"] == 1


def test_web_object_graph_remains_android_object_free() -> None:
    for stage in BACKEND_STAGES["web"]:
        objects = _stage("web", stage)["backend_objects"]
        assert isinstance(objects, dict)
        assert not [name for name in objects if name.startswith("notebooklm._android")]


def test_static_scanner_resolves_relative_local_type_and_dynamic_imports() -> None:
    imports, dynamic = _scan_static_source(
        """
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .._web.rows import ProjectRow

def load():
    from .._android import codec
    import importlib as loader
    return loader.import_module(".rows", "notebooklm._web")
""",
        module="notebooklm._types.synthetic",
        package="notebooklm._types",
        modules={"notebooklm._android.codec", "notebooklm._web.rows"},
    )

    selected = [
        (item.target, item.scope, item.scope_kind, item.type_only)
        for item in imports
        if item.target.startswith("notebooklm.")
    ]
    assert selected == [
        ("notebooklm._web.rows", None, "module", True),
        ("notebooklm._android.codec", "load", "function", False),
    ]
    assert [(item.callee, item.target, item.scope, item.type_only) for item in dynamic] == [
        ("loader.import_module", "notebooklm._web.rows", "load", False)
    ]


def test_static_projection_excludes_generated_android_protobuf(tmp_path: Path) -> None:
    source_root = tmp_path / "notebooklm"
    generated = source_root / "_android" / "proto" / "generated.py"
    authored = source_root / "_web" / "authored.py"
    generated.parent.mkdir(parents=True)
    authored.parent.mkdir(parents=True)
    generated.write_text("import notebooklm.client\n", encoding="utf-8")
    authored.write_text("from .. import client\n", encoding="utf-8")

    projection = build_static_projection(source_root)

    assert projection["summary"]["authored_modules"] == 1
    assert projection["subsystems"] == {"web": {"lines": 1, "modules": 1}}


def test_coupling_growth_policies_reject_replacement_and_count_growth() -> None:
    previous_runtime = {
        "public_entries": {
            "package": {"module_delta": ["notebooklm"], "optional_android_module_delta": []}
        },
        "backends": {
            "web": {
                "stages": {
                    "import_client": {
                        "module_delta": ["notebooklm"],
                        "optional_android_module_delta": [],
                        "backend_objects": {"notebooklm._web.Owner": 1},
                        "network_destinations": {},
                        "profile_reads": {},
                        "profile_writes": {},
                        "lifecycle": {"transports": [], "loop_participants": []},
                    }
                }
            }
        },
    }
    current_runtime = {
        "public_entries": {
            "package": {
                "module_delta": ["notebooklm", "notebooklm._web.new"],
                "optional_android_module_delta": [],
            }
        },
        "backends": {
            "web": {
                "stages": {
                    "import_client": {
                        "module_delta": ["notebooklm"],
                        "optional_android_module_delta": [],
                        "backend_objects": {"notebooklm._web.Owner": 2},
                        "network_destinations": {},
                        "profile_reads": {},
                        "profile_writes": {},
                        "lifecycle": {"transports": [], "loop_participants": []},
                    }
                }
            }
        },
    }
    assert runtime_projection_growth(previous_runtime, current_runtime) == [
        "package.module_delta: new notebooklm._web.new",
        "web.import_client.backend_objects.notebooklm._web.Owner: 1 -> 2",
    ]

    edge = {
        "source": "notebooklm.client",
        "target": "notebooklm._web.runtime",
        "kind": "from",
        "scope": None,
        "scope_kind": "module",
        "type_only": False,
        "lineno": 1,
    }
    assert static_projection_growth(
        {"edges": [], "dynamic_imports": []},
        {"edges": [edge], "dynamic_imports": []},
    ) == [
        'edges: new {"kind": "from", "scope": null, "scope_kind": "module", '
        '"source": "notebooklm.client", "target": "notebooklm._web.runtime", '
        '"type_only": false}'
    ]
