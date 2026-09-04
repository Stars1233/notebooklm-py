"""Dependency-bottom paired cookie loading for auth storage.

This leaf owns the one-sample projection used by profile reads: a raw
``storage_state.json`` sample becomes both the live ``httpx`` jar and the
typed persistence baseline.  Compatibility helpers in :mod:`cookies` retain
their historical identities and delegate here; this module deliberately does
not import that compatibility module.
"""

from __future__ import annotations

import copy
import http.cookiejar
import json
import logging
import math
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import httpx

from ..paths import get_storage_path
from . import cookie_contract as _cookie_contract
from . import cookie_policy as _cookie_policy
from . import cookie_semantics as _cookie_semantics
from .cookie_types import Cookie, CookieIdentity, CookieJar
from .paths import resolve_auth_json_env

logger = logging.getLogger("notebooklm.auth")

MINIMUM_REQUIRED_COOKIES = _cookie_policy.MINIMUM_REQUIRED_COOKIES
_EXTRACTION_HINT = _cookie_policy._EXTRACTION_HINT
_is_allowed_auth_domain = _cookie_policy._is_allowed_auth_domain
_validate_required_cookies = _cookie_policy._validate_required_cookies
RequiredCookieValidationError = _cookie_policy.RequiredCookieValidationError
_CookieRowError = _cookie_semantics.CookieRowError
_PSIDTS_COOKIE = "__Secure-1PSIDTS"
_CookieConverter = Callable[[dict[str, Any]], http.cookiejar.Cookie]


class StorageStateValidationError(ValueError):
    """Storage JSON has no usable Playwright ``cookies`` list."""


class _SanitizedCookieEntry(dict[str, Any]):
    """Marker for a row already sanitized within the current load operation."""


@dataclass(frozen=True, slots=True, repr=False)
class _LoadedCookiePair:
    """One raw-state sample projected to live and persistence-safe forms."""

    live: httpx.Cookies = field(repr=False)
    baseline: CookieJar = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.live, httpx.Cookies) or not isinstance(self.baseline, CookieJar):
            raise TypeError("loaded cookie pair fields are invalid")
        object.__setattr__(self, "baseline", CookieJar(tuple(self.baseline)))


def _bounded_row_field(entry: Any, field: str) -> str:
    if not isinstance(entry, dict):
        return type(entry).__name__
    value = entry.get(field)
    return value[:80] if isinstance(value, str) else type(value).__name__


def _sanitize_cookie_entry(entry: Any) -> dict[str, Any] | None:
    """Sanitize one storage row and emit only redacted diagnostics."""
    if isinstance(entry, _SanitizedCookieEntry):
        return entry
    try:
        return _cookie_semantics.sanitize_cookie_entry(entry)
    except _CookieRowError as exc:
        logger.debug(
            "Skipping malformed cookie row name=%s domain=%s row_type=%s error=%s",
            _bounded_row_field(entry, "name"),
            _bounded_row_field(entry, "domain"),
            type(entry).__name__,
            type(exc).__name__,
        )
        return None


def _sanitized_auth_entries(storage_state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return structurally safe, allowlisted rows from a storage state."""
    raw_entries = storage_state.get("cookies", [])
    if not isinstance(raw_entries, list):
        return []
    entries: list[dict[str, Any]] = []
    for raw_entry in raw_entries:
        entry = _sanitize_cookie_entry(raw_entry)
        if entry is not None and _is_allowed_auth_domain(entry["domain"]):
            entries.append(entry)
    return entries


def _load_storage_state(path: Path | None = None) -> dict[str, Any]:
    """Load Playwright storage state using the canonical auth precedence."""
    if path is not None:
        if not path.exists():
            raise FileNotFoundError(
                f"Storage file not found: {path}\nRun 'notebooklm login' to authenticate first."
            )
        storage_state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(storage_state, dict) or not isinstance(
            storage_state.get("cookies"), list
        ):
            raise StorageStateValidationError(
                "Storage state must contain a 'cookies' list.\n"
                'Expected format: {"cookies": [{"name": "SID", "value": "...", ...}]}'
            )
        return storage_state

    env_auth_json = resolve_auth_json_env()
    if env_auth_json is not None:
        return _load_storage_state_from_env_value(env_auth_json)

    storage_path = get_storage_path()
    if not storage_path.exists():
        raise FileNotFoundError(
            f"Storage file not found: {storage_path}\nRun 'notebooklm login' to authenticate first."
        )
    storage_state = json.loads(storage_path.read_text(encoding="utf-8"))
    if not isinstance(storage_state, dict) or not isinstance(storage_state.get("cookies"), list):
        raise StorageStateValidationError(
            "Storage state must contain a 'cookies' list.\n"
            'Expected format: {"cookies": [{"name": "SID", "value": "...", ...}]}'
        )
    return storage_state


def _load_storage_state_from_env_value(env_auth_json: str) -> dict[str, Any]:
    """Parse one already-captured inline-auth value."""
    auth_json = env_auth_json.strip()
    if not auth_json:
        raise StorageStateValidationError(
            "NOTEBOOKLM_AUTH_JSON environment variable is set but empty.\n"
            "Provide valid Playwright storage state JSON or unset the variable."
        )
    try:
        storage_state = json.loads(auth_json)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in NOTEBOOKLM_AUTH_JSON environment variable: {exc}\n"
            "Ensure the value is valid Playwright storage state JSON."
        ) from exc
    if not isinstance(storage_state, dict) or not isinstance(storage_state.get("cookies"), list):
        raise StorageStateValidationError(
            "NOTEBOOKLM_AUTH_JSON must contain valid Playwright storage state "
            "with a 'cookies' key.\n"
            'Expected format: {"cookies": [{"name": "SID", "value": "...", ...}]}'
        )
    return storage_state


def _cookie_is_http_only(cookie: Any) -> bool:
    return _cookie_semantics.cookie_is_http_only(cookie)


def _cookie_from_normalized_entry(
    normalized: dict[str, Any], *, http_only_key: str
) -> http.cookiejar.Cookie:
    return _cookie_semantics.cookie_from_normalized_entry(
        normalized,
        http_only_key=http_only_key,
    )


def _cookie_header_names(header: str) -> set[str]:
    return {part.split("=", 1)[0].strip() for part in header.split(";") if "=" in part}


def _allowed_cookie_name(entry: Any) -> str | None:
    normalized = _sanitize_routing_entry(entry)
    if normalized is None or not _is_allowed_auth_domain(normalized["domain"]):
        return None
    return normalized["name"]


def _sanitize_routing_entry(entry: Any) -> dict[str, Any] | None:
    """Revalidate a row for routing, including rows marked by a source pass."""
    try:
        return _cookie_semantics.sanitize_cookie_entry(entry)
    except _CookieRowError as exc:
        logger.debug(
            "Skipping malformed cookie row name=%s domain=%s row_type=%s error=%s",
            _bounded_row_field(entry, "name"),
            _bounded_row_field(entry, "domain"),
            type(entry).__name__,
            type(exc).__name__,
        )
        return None


def _try_cookie(entry: Any, converter: _CookieConverter) -> http.cookiejar.Cookie | None:
    try:
        _cookie_semantics.validate_cookie_shape(entry)
    except _cookie_semantics.CookieRowError as exc:
        logger.debug(
            "Skipping malformed cookie row name=%s domain=%s row_type=%s error=%s",
            _bounded_row_field(entry, "name"),
            _bounded_row_field(entry, "domain"),
            type(entry).__name__,
            type(exc).__name__,
        )
        return None
    try:
        return converter(entry)
    except (ValueError, TypeError, OverflowError) as exc:
        logger.debug(
            "Skipping unusable cookie row name=%s domain=%s error=%s",
            _bounded_row_field(entry, "name"),
            _bounded_row_field(entry, "domain"),
            type(exc).__name__,
        )
        return None


def _is_expired(cookie: http.cookiejar.Cookie, now: float | None) -> bool:
    return cookie.is_expired(None if now is None else math.floor(now))


def _iter_routable_psidts_cookies(
    entries: list[dict[str, Any]],
    *,
    to_cookie: _CookieConverter,
    now: float | None = None,
) -> Iterator[http.cookiejar.Cookie]:
    live: dict[tuple[str, str, str], http.cookiejar.Cookie] = {}
    dead: set[tuple[str, str, str]] = set()
    for entry in entries:
        if _allowed_cookie_name(entry) != _PSIDTS_COOKIE:
            continue
        cookie = _try_cookie(entry, to_cookie)
        if cookie is None:
            continue
        identity = (cookie.name, cookie.domain, cookie.path)
        if _is_expired(cookie, now):
            dead.add(identity)
        else:
            live[identity] = cookie
    for identity, cookie in live.items():
        if identity not in dead:
            yield cookie


def _cookies_route_psidts(cookies: Iterable[http.cookiejar.Cookie]) -> bool:
    jar = httpx.Cookies()
    found = False
    for cookie in cookies:
        if cookie.name != _PSIDTS_COOKIE or not cookie.value:
            continue
        jar.jar.set_cookie(cookie)
        found = True
    if not found:
        return False
    request = httpx.Request("POST", _cookie_contract.KEEPALIVE_ROTATE_URL)
    jar.set_cookie_header(request)
    return _PSIDTS_COOKIE in _cookie_header_names(request.headers.get("cookie", ""))


def _psidts_routes_to_rotate(
    entries: list[dict[str, Any]],
    *,
    to_cookie: _CookieConverter,
    now: float | None = None,
) -> bool:
    probes = []
    for cookie in _iter_routable_psidts_cookies(entries, to_cookie=to_cookie, now=now):
        probe = copy.copy(cookie)
        probe.expires = None
        probes.append(probe)
    return _cookies_route_psidts(probes)


def _load_cookie_pair_pure(
    path: Path | None = None,
    *,
    require_routable: bool = True,
    routable_check: Callable[..., bool] | None = None,
    converter: Callable[..., http.cookiejar.Cookie] | None = None,
) -> _LoadedCookiePair:
    """Load one raw state sample into paired live and typed projections."""
    storage_state = _load_storage_state(path)
    return _build_cookie_pair_from_storage_state(
        storage_state,
        require_routable=require_routable,
        routable_check=routable_check,
        converter=converter,
    )


def _build_cookie_pair_from_storage_state(
    storage_state: dict[str, Any],
    *,
    context: str = "",
    require_routable: bool,
    routable_check: Callable[..., bool] | None = None,
    converter: Callable[..., http.cookiejar.Cookie] | None = None,
) -> _LoadedCookiePair:
    """Project one already-loaded state without losing cookie provenance."""
    entries: list[dict[str, Any]] = [
        _SanitizedCookieEntry(entry) for entry in _sanitized_auth_entries(storage_state)
    ]
    convert = converter or _cookie_from_normalized_entry
    converted_rows: list[tuple[dict[str, Any], http.cookiejar.Cookie | None]] = []
    for entry in entries:
        try:
            converted = convert(entry, http_only_key="httpOnly")
        except (ValueError, TypeError, OverflowError) as exc:
            logger.debug(
                "Skipping unusable cookie row name=%s domain=%s error=%s",
                _bounded_row_field(entry, "name"),
                _bounded_row_field(entry, "domain"),
                type(exc).__name__,
            )
            converted_rows.append((entry, None))
            continue
        converted_rows.append((entry, converted))

    live = httpx.Cookies()
    baseline: list[Cookie] = []
    seen_keys: set[CookieIdentity] = set()
    converted_by_row = {id(entry): converted for entry, converted in converted_rows}
    for normalized, selected_cookie in converted_rows:
        if selected_cookie is None:
            continue
        key = CookieIdentity(normalized["name"], normalized["domain"], normalized["path"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        live.jar.set_cookie(selected_cookie)
        raw_same_site = normalized.get("sameSite", normalized.get("same_site"))
        baseline.append(
            Cookie(
                name=selected_cookie.name,
                domain=selected_cookie.domain,
                path=selected_cookie.path or "/",
                value=cast(str, selected_cookie.value),
                expires=selected_cookie.expires,
                secure=bool(selected_cookie.secure),
                http_only=_cookie_is_http_only(selected_cookie),
                same_site=raw_same_site if isinstance(raw_same_site, str) else None,
            )
        )

    def reuse_converted(entry: dict[str, Any]) -> http.cookiejar.Cookie:
        converted = converted_by_row.get(id(entry))
        if converted is None:
            raise ValueError("cookie row was unusable")
        return converted

    _validate_required_cookies({entry["name"] for entry in entries}, context=context)
    if require_routable:
        check = routable_check or _psidts_routes_to_rotate
        if check(entries, to_cookie=reuse_converted):
            return _LoadedCookiePair(live=live, baseline=CookieJar(baseline))
        raise RequiredCookieValidationError(
            f"Required cookie __Secure-1PSIDTS is not routable{context}.\n{_EXTRACTION_HINT}",
            reason="psidts_unroutable",
        )
    return _LoadedCookiePair(live=live, baseline=CookieJar(baseline))
