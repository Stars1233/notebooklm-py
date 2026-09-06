"""Behavioral probes use the same boundary predicate as the ordinary PR lane."""

import pytest

from ._adapter_import_boundary import adapter_violations, scan_source


@pytest.mark.parametrize("adapter,peer", [("cli", "mcp"), ("mcp", "server"), ("server", "cli")])
@pytest.mark.parametrize(
    "shape", ["absolute", "relative", "type_only", "dynamic", "dynamic_relative"]
)
def test_forbidden_adapter_edges_are_rejected(adapter: str, peer: str, shape: str) -> None:
    source = {
        "absolute": f"from notebooklm.{peer} import api",
        "relative": f"from .. import {peer}",
        "type_only": f"if TYPE_CHECKING:\n    from ..{peer} import api",
        "dynamic": f"__import__('notebooklm.{peer}.api')",
        "dynamic_relative": f"importlib.import_module('..{peer}.api', __package__)",
    }[shape]
    assert adapter_violations(
        scan_source(source, package=f"notebooklm.{adapter}"), relative=f"{adapter}/example.py"
    )


@pytest.mark.parametrize("adapter,folder", [("mcp", "tools"), ("server", "routes")])
@pytest.mark.parametrize("symbol", ["delete_batch", "*", "preserve_batch_other_failure"])
def test_settlement_exception_does_not_admit_other_symbols(
    adapter: str, folder: str, symbol: str
) -> None:
    source = f"from notebooklm._source.batch import {symbol}"
    assert adapter_violations(
        scan_source(source, package=f"notebooklm.{adapter}.{folder}"),
        relative=f"{adapter}/{folder}/sources.py",
    )


@pytest.mark.parametrize("adapter,folder", [("mcp", "tools"), ("server", "routes")])
@pytest.mark.parametrize(
    "symbol", ["preserve_batch_call_failure", "preserve_batch_projection_failure"]
)
def test_exact_settlement_symbols_are_confined_to_source_adapter(
    adapter: str, folder: str, symbol: str
) -> None:
    source = f"from ..._source.batch import {symbol}"
    imports = scan_source(source, package=f"notebooklm.{adapter}.{folder}")
    assert not adapter_violations(imports, relative=f"{adapter}/{folder}/sources.py")
    assert adapter_violations(imports, relative=f"{adapter}/{folder}/notebooks.py")


@pytest.mark.parametrize(
    "source",
    [
        "from notebooklm._web import assembly",
        "importlib.import_module('.._web.assembly', package='notebooklm.mcp')",
        "from notebooklm.types import _secret",
        "from notebooklm import _atomic_io",
        "from notebooklm.rpc.types import ArtifactType",
    ],
)
def test_private_domain_and_rpc_edges_are_rejected(source: str) -> None:
    assert adapter_violations(
        scan_source(source, package="notebooklm.mcp"), relative="mcp/server.py"
    )


def test_public_facades_and_local_private_modules_are_allowed() -> None:
    source = "from ...types import Artifact\nfrom ...io import atomic_write_json\nfrom ._payloads import render\nfrom ..._app.download import execute_download"
    assert not adapter_violations(
        scan_source(source, package="notebooklm.mcp.tools"), relative="mcp/tools/studio.py"
    )
