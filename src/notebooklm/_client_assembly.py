"""Import-light backend selector shared by production and the test factory."""

from __future__ import annotations

import dataclasses
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

import httpx

from ._client_compat import WebSeamOverrides, _install_android_web_compatibility
from ._client_contracts import BackendAssembly, BackendName, CookieRotator, CookieSaver
from ._runtime.config import (
    AUTO_READ_TIMEOUT,
    DEFAULT_CHAT_RESPONSE_MAX_BYTES,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_KEEPALIVE_MIN_INTERVAL,
    DEFAULT_MAX_CONCURRENT_RPCS,
    DEFAULT_MAX_CONCURRENT_UPLOADS,
    DEFAULT_TIMEOUT,
    validate_read_timeout_kwarg,
)
from ._runtime.error_injection import _refuse_synthetic_error_outside_test_context
from ._runtime.init import validate_shared_runtime_config
from ._runtime.lifecycle import ClientLifecycle
from .auth import AuthTokens

if TYPE_CHECKING:
    from ._android.auth import MasterTokenReader, OAuthMinter
    from .client import NotebookLMClient
    from .types import ConnectionLimits, RpcTelemetryEvent

logger = logging.getLogger("notebooklm.backend")


@dataclass(frozen=True)
class BackendPreference:
    """One construction-time backend preference and how it was selected."""

    preferred: BackendName
    reason: Literal["explicit", "env", "default"]


def resolve_backend_preference(*, explicit: str | None, env: str | None) -> BackendPreference:
    """Resolve and validate the backend preference without performing I/O."""

    value: str
    reason: Literal["explicit", "env", "default"]
    if explicit is not None:
        value = explicit
        reason = "explicit"
    elif env is not None:
        value = env
        reason = "env"
    else:
        value = "web"
        reason = "default"
    if value not in ("web", "android"):
        raise ValueError(
            f"Invalid NotebookLM backend {value!r}: expected 'web' or 'android'. "
            "The aliases 'mobile' and 'auto' are not supported."
        )
    return BackendPreference(preferred=cast(BackendName, value), reason=reason)


class _UnsetType:
    """Sentinel for test-factory overrides whose ``None`` value is meaningful."""


_UNSET = _UnsetType()


def _install_lifecycle(client: NotebookLMClient, assembly: BackendAssembly) -> None:
    lifecycle = ClientLifecycle(
        supervisor=assembly.collaborators.call_supervisor,
        transports=assembly.transports,
        loop_participants=assembly.loop_participants,
    )
    client._collaborators = dataclasses.replace(assembly.collaborators, _lifecycle=lifecycle)
    client._backends = assembly.backends
    client._rpc_call_deprecation_warned = False
    if assembly.bind_collaborators is not None:
        assembly.bind_collaborators(client._collaborators)


def _assemble_client(
    client: NotebookLMClient,
    *,
    auth: AuthTokens,
    timeout: float = DEFAULT_TIMEOUT,
    storage_path: Path | None = None,
    keepalive: float | None = None,
    keepalive_min_interval: float = DEFAULT_KEEPALIVE_MIN_INTERVAL,
    rate_limit_max_retries: int = 3,
    server_error_max_retries: int = 3,
    limits: ConnectionLimits | None = None,
    max_concurrent_uploads: int | None = DEFAULT_MAX_CONCURRENT_UPLOADS,
    max_concurrent_rpcs: int | None = DEFAULT_MAX_CONCURRENT_RPCS,
    upload_timeout: httpx.Timeout | None = None,
    on_rpc_event: Callable[[RpcTelemetryEvent], object] | None = None,
    cookie_saver: CookieSaver | None = None,
    cookie_rotator: CookieRotator | None = None,
    chat_timeout: float | None = AUTO_READ_TIMEOUT,
    import_research_timeout: float | None = AUTO_READ_TIMEOUT,
    chat_response_max_bytes: int | None = DEFAULT_CHAT_RESPONSE_MAX_BYTES,
    backend: BackendName | None = None,
    refresh_callback: Callable[[int], Awaitable[AuthTokens]] | None | _UnsetType = _UNSET,
    refresh_retry_delay: float = 0.2,
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    keepalive_storage_path: Path | None | _UnsetType = _UNSET,
    decode_response: Callable[..., Any] | None = None,
    sleep: Callable[[float], Awaitable[Any]] | None = None,
    is_auth_error: Callable[[Exception], bool] | None = None,
    async_client_factory: Callable[..., httpx.AsyncClient] | None = None,
    master_token_reader: MasterTokenReader | _UnsetType = _UNSET,
    oauth_minter: OAuthMinter | _UnsetType = _UNSET,
) -> None:
    """Normalize root-owned inputs, select one backend, and freeze its lifecycle."""

    client._backend_preference = resolve_backend_preference(
        explicit=backend,
        env=None if backend is not None else os.environ.get("NOTEBOOKLM_BACKEND"),
    )
    if storage_path is not None:
        storage_path = Path(storage_path)
        if auth.storage_path != storage_path:
            auth = dataclasses.replace(auth, storage_path=storage_path)

    client._auth = auth
    client._account_email_cache = None
    client._account_email_cache_route = None

    use_default_refresh_callback = isinstance(refresh_callback, _UnsetType)
    if use_default_refresh_callback:
        effective_refresh_callback = None
    else:
        effective_refresh_callback = cast(
            Callable[[int], Awaitable[AuthTokens]] | None,
            refresh_callback,
        )

    if isinstance(keepalive_storage_path, _UnsetType):
        derived_keepalive_path: Path | None = auth.storage_path
        if derived_keepalive_path is not None:
            derived_keepalive_path = Path(derived_keepalive_path).expanduser().resolve()
        keepalive_storage_path = derived_keepalive_path

    if client._backend_preference.preferred == "web" and max_concurrent_rpcs is not None:
        from .types import ConnectionLimits

        effective_limits = limits if limits is not None else ConnectionLimits()
        if max_concurrent_rpcs > effective_limits.max_connections:
            raise ValueError(
                "max_concurrent_rpcs must be <= limits.max_connections "
                f"(got max_concurrent_rpcs={max_concurrent_rpcs}, "
                f"max_connections={effective_limits.max_connections}). "
                "A semaphore wider than the connection pool surfaces "
                "saturation as opaque httpx.PoolTimeout instead of clean back-pressure."
            )
    if chat_response_max_bytes is not None and chat_response_max_bytes < 1:
        raise ValueError(
            f"chat_response_max_bytes must be >= 1 when supplied (got {chat_response_max_bytes!r})"
        )
    chat_timeout = validate_read_timeout_kwarg(chat_timeout, name="chat_timeout")
    import_research_timeout = validate_read_timeout_kwarg(
        import_research_timeout,
        name="import_research_timeout",
    )

    shared_config = validate_shared_runtime_config(max_concurrent_rpcs=max_concurrent_rpcs)
    _refuse_synthetic_error_outside_test_context()

    if client._backend_preference.preferred == "android":
        ignored_web_options: list[str] = []
        if keepalive is not None:
            ignored_web_options.append("keepalive")
        if keepalive_min_interval != DEFAULT_KEEPALIVE_MIN_INTERVAL:
            ignored_web_options.append("keepalive_min_interval")
        if cookie_saver is not None:
            ignored_web_options.append("cookie_saver")
        if cookie_rotator is not None:
            ignored_web_options.append("cookie_rotator")
        if limits is not None:
            ignored_web_options.append("limits")
        if ignored_web_options:
            logger.debug(
                "Android backend ignores Web-only options: %s",
                ", ".join(ignored_web_options),
            )

        from ._android.assembly import assemble_android_backend

        seam_overrides = WebSeamOverrides(
            decode_response=decode_response,
            sleep=sleep,
            is_auth_error=is_auth_error,
        )
        client._seams = seam_overrides

        assembly = assemble_android_backend(
            client,
            profile_path=Path(auth.storage_path) if auth.storage_path is not None else None,
            master_token_reader=(
                None if isinstance(master_token_reader, _UnsetType) else master_token_reader
            ),
            oauth_minter=None if isinstance(oauth_minter, _UnsetType) else oauth_minter,
            timeout=timeout,
            refresh_retry_delay=refresh_retry_delay,
            rate_limit_max_retries=rate_limit_max_retries,
            server_error_max_retries=server_error_max_retries,
            max_concurrent_uploads=max_concurrent_uploads,
            upload_timeout=upload_timeout,
            chat_timeout=chat_timeout,
            import_research_timeout=import_research_timeout,
            chat_response_max_bytes=chat_response_max_bytes,
            sleep=sleep,
            shared_config=shared_config,
            on_rpc_event=on_rpc_event,
        )
        _install_android_web_compatibility(
            client,
            assembly,
            auth=auth,
            shared_config=shared_config,
            seam_overrides=seam_overrides,
            refresh_callback=effective_refresh_callback,
            use_default_refresh_callback=use_default_refresh_callback,
            timeout=timeout,
            refresh_retry_delay=refresh_retry_delay,
            rate_limit_max_retries=rate_limit_max_retries,
            server_error_max_retries=server_error_max_retries,
            max_concurrent_uploads=max_concurrent_uploads,
            async_client_factory=async_client_factory,
        )
        return

    from ._web.assembly import assemble_web_backend

    assembly = assemble_web_backend(
        client,
        auth=auth,
        timeout=timeout,
        storage_path=storage_path,
        keepalive=keepalive,
        keepalive_min_interval=keepalive_min_interval,
        rate_limit_max_retries=rate_limit_max_retries,
        server_error_max_retries=server_error_max_retries,
        limits=limits,
        max_concurrent_uploads=max_concurrent_uploads,
        max_concurrent_rpcs=max_concurrent_rpcs,
        upload_timeout=upload_timeout,
        on_rpc_event=on_rpc_event,
        cookie_saver=cookie_saver,
        cookie_rotator=cookie_rotator,
        chat_timeout=chat_timeout,
        import_research_timeout=import_research_timeout,
        chat_response_max_bytes=chat_response_max_bytes,
        refresh_callback=effective_refresh_callback,
        use_default_refresh_callback=use_default_refresh_callback,
        refresh_retry_delay=refresh_retry_delay,
        connect_timeout=connect_timeout,
        keepalive_storage_path=keepalive_storage_path,
        async_client_factory=async_client_factory,
        decode_response=decode_response,
        sleep=sleep,
        is_auth_error=is_auth_error,
        shared_config=shared_config,
    )
    _install_lifecycle(client, assembly)


__all__ = ["BackendName", "BackendPreference", "_assemble_client", "resolve_backend_preference"]
