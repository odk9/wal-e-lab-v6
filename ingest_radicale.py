"""
ingest_radicale.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de Kozea/Radicale dans la KB Qdrant V6.

Focus : CORE patterns CalDAV server (plugin architecture, WebDAV protocol,
iCalendar item model, configuration schema, permissions system).

Usage:
    .venv/bin/python3 ingest_radicale.py
"""

from __future__ import annotations

import subprocess
import time
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from embedder import embed_documents_batch, embed_query
from kb_utils import build_payload, check_charte_violations, make_uuid, query_kb, audit_report

# ─── Constantes ──────────────────────────────────────────────────────────────
REPO_URL = "https://github.com/Kozea/Radicale.git"
REPO_NAME = "Kozea/Radicale"
REPO_LOCAL = "/tmp/radicale"
LANGUAGE = "python"
FRAMEWORK = "wsgi"
STACK = "wsgi+vobject+caldav"
CHARTE_VERSION = "1.0"
TAG = "Kozea/Radicale"
SOURCE_REPO = "https://github.com/Kozea/Radicale"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Radicale = CalDAV/CardDAV server.
# Patterns CORE : plugin system, WebDAV protocol, calendar model, config schema, perms.
# U-5 : Item → Xxx, collections → xxxs, user → account

PATTERNS: list[dict] = [
    # ── 1. Plugin registry + config-driven loading ────────────────────────────
    {
        "normalized_code": """\
import hashlib
import threading
import time
from typing import Sequence, final
from urllib.parse import unquote


INTERNAL_TYPES: Sequence[str] = (
    "none", "remote_account", "http_x_remote_account",
    "http_remote_account", "denyall", "htpasswd",
    "ldap", "imap", "oauth2", "pam", "dovecot",
)

CACHE_LOGIN_TYPES: Sequence[str] = (
    "dovecot", "ldap", "htpasswd", "imap", "oauth2", "pam",
)


def load(configuration: "XxxConfiguration") -> "BaseAuth":
    \"\"\"Load the authentication module chosen in configuration.\"\"\"
    _type = configuration.get("auth", "type")
    return utils.load_plugin(
        INTERNAL_TYPES, "xxx.auth", _type, configuration,
    )
""",
        "function": "plugin_registry_config_driven",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "radicale/auth/__init__.py",
    },
    # ── 2. Auth base class — pluggable backend interface ──────────────────────
    {
        "normalized_code": """\
import hashlib
import threading
import time
from typing import Sequence, Tuple, Union


class BaseAuth:
    \"\"\"Abstract base for authentication backends.

    Subclasses must implement _login(login, password) -> str.
    Built-in caching via SHA3-512 with separate TTLs for success/failure.
    \"\"\"

    def __init__(self, configuration: "XxxConfiguration") -> None:
        self._lc_username = configuration.get("auth", "lc_username")
        self._uc_username = configuration.get("auth", "uc_username")
        self._strip_domain = configuration.get("auth", "strip_domain")
        self._auth_delay = configuration.get("auth", "delay")
        self._cache_logins = configuration.get("auth", "cache_logins")
        self._cache_successful: dict[str, tuple[str, float]] = {}
        self._cache_failed: dict[str, float] = {}
        self._lock = threading.Lock()

    def get_external_login(self, environ: dict) -> Union[Tuple[str, str], Tuple[()]]:
        \"\"\"Hook for reverse-proxy SSO (override in subclass).\"\"\"
        return ()

    def _login(self, login: str, password: str) -> str:
        \"\"\"Authenticate. Return username if OK, empty string if fail.\"\"\"
        raise NotImplementedError

    def login(self, login: str, password: str) -> str:
        \"\"\"Public login with caching, delay, and username normalization.\"\"\"
        if self._lc_username:
            login = login.lower()
        if self._uc_username:
            login = login.upper()
        if self._strip_domain and "@" in login:
            login = login.split("@")[0]
        cache_key = hashlib.sha3_512(
            f"{login}:{password}".encode()
        ).hexdigest()
        with self._lock:
            if cache_key in self._cache_successful:
                cached_login, ts = self._cache_successful[cache_key]
                if time.time() - ts < self._cache_ttl_success:
                    return cached_login
            if cache_key in self._cache_failed:
                if time.time() - self._cache_failed[cache_key] < self._cache_ttl_fail:
                    time.sleep(self._auth_delay)
                    return ""
        result = self._login(login, password)
        with self._lock:
            if result:
                self._cache_successful[cache_key] = (result, time.time())
            else:
                self._cache_failed[cache_key] = time.time()
                time.sleep(self._auth_delay)
        return result
""",
        "function": "auth_base_class_pluggable",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "radicale/auth/__init__.py",
    },
    # ── 3. Character-based permissions system ─────────────────────────────────
    {
        "normalized_code": """\
from typing import Sequence


class BaseRights:
    \"\"\"Abstract base for authorization (permissions) backends.

    Permission characters:
      R/r = read (R=general, r=calendar-specific)
      W/w = write (W=general, w=calendar-specific)
      D/d = delete permission
      O/o = overwrite permission
    \"\"\"

    INTERNAL_TYPES: Sequence[str] = (
        "authenticated", "owner_write", "owner_only", "from_file",
    )

    def authorization(self, account: str, path: str) -> str:
        \"\"\"Return permission string for account+path.

        Returns string of permission characters (e.g., 'RrWw').
        \"\"\"
        raise NotImplementedError

    @staticmethod
    def intersect(a: str, b: str) -> str:
        \"\"\"Compute intersection of two permission strings.\"\"\"
        return "".join(c for c in a if c in b)
""",
        "function": "permissions_char_based_system",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "radicale/rights/__init__.py",
    },
    # ── 4. iCalendar data model — lazy-loading with cache warming ─────────────
    {
        "normalized_code": """\
import hashlib
from typing import Optional, Tuple


class Xxx:
    \"\"\"Calendar/addressbook entry with lazy evaluation.

    Accepts either raw text or parsed vobject — never both.
    Properties are computed on first access and cached.
    \"\"\"

    collection: Optional["BaseCollection"]
    href: Optional[str]
    last_modified: Optional[str]

    _text: Optional[str]
    _vobject: Optional[object]
    _etag: Optional[str]
    _uid: Optional[str]
    _component_name: Optional[str]
    _time_range: Optional[Tuple[int, int]]

    def __init__(
        self,
        collection_path: Optional[str] = None,
        collection: Optional["BaseCollection"] = None,
        vobject: Optional[object] = None,
        href: Optional[str] = None,
        last_modified: Optional[str] = None,
        text: Optional[str] = None,
        etag: Optional[str] = None,
        uid: Optional[str] = None,
        component_name: Optional[str] = None,
        time_range: Optional[Tuple[int, int]] = None,
    ) -> None:
        if text is None and vobject is None:
            raise ValueError("At least one of 'text' or 'vobject' must be set")
        self._text = text
        self._vobject = vobject
        self._etag = etag
        self._uid = uid
        self._component_name = component_name
        self._time_range = time_range
        self.collection = collection
        self.href = href
        self.last_modified = last_modified

    @property
    def etag(self) -> str:
        \"\"\"SHA256 hash of serialized text.\"\"\"
        if self._etag is None:
            self._etag = hashlib.sha256(self.serialize().encode()).hexdigest()
        return self._etag

    @property
    def uid(self) -> str:
        \"\"\"Extract UID from parsed vobject.\"\"\"
        if self._uid is None:
            self._uid = get_uid_from_object(self.vobject)
        return self._uid

    def serialize(self) -> str:
        \"\"\"Serialize to iCalendar/vCard text.\"\"\"
        if self._text is not None:
            return self._text
        return self._vobject.serialize()

    def prepare(self) -> None:
        \"\"\"Warm all cached properties before returning to client.\"\"\"
        _ = self.serialize()
        _ = self.etag
        _ = self.uid
        _ = self._component_name
        _ = self._time_range
""",
        "function": "icalendar_data_model_lazy_cache",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "radicale/item/__init__.py",
    },
    # ── 5. Abstract storage interface — pluggable backends ────────────────────
    {
        "normalized_code": """\
from typing import Iterable, Optional, overload


class BaseCollection:
    \"\"\"Abstract base for a calendar/addressbook collection.

    Defines the interface for storage backends (file, DB, cloud).
    \"\"\"

    @property
    def path(self) -> str:
        \"\"\"Collection path (e.g., '/account/calendar.ics').\"\"\"
        raise NotImplementedError

    def get_all(self) -> Iterable["Xxx"]:
        \"\"\"Return all entries in the collection.\"\"\"
        raise NotImplementedError

    def get_multi(self, hrefs: list[str]) -> Iterable[tuple[str, Optional["Xxx"]]]:
        \"\"\"Return specific entries by href (None if missing).\"\"\"
        raise NotImplementedError

    def upload(self, href: str, xxx: "Xxx") -> "Xxx":
        \"\"\"Upload/replace an entry. Returns the stored version.\"\"\"
        raise NotImplementedError

    def delete(self, href: str | None = None) -> None:
        \"\"\"Delete an entry or the entire collection.\"\"\"
        raise NotImplementedError

    @property
    def etag(self) -> str:
        \"\"\"Collection-level etag (changes on any modification).\"\"\"
        raise NotImplementedError

    def get_meta(self, key: str | None = None) -> object:
        \"\"\"Get collection metadata (displayName, color, etc.).\"\"\"
        raise NotImplementedError

    def set_meta(self, props: dict) -> None:
        \"\"\"Set collection metadata.\"\"\"
        raise NotImplementedError

    def serialize(self) -> str:
        \"\"\"Serialize entire collection (with VTIMEZONE deduplication).\"\"\"
        raise NotImplementedError


class BaseStorage:
    \"\"\"Abstract base for the storage layer managing collections.\"\"\"

    def discover(self, path: str, depth: str = "0") -> Iterable["BaseCollection"]:
        \"\"\"Discover collections at path (WebDAV PROPFIND depth).\"\"\"
        raise NotImplementedError

    def create_collection(
        self, href: str, props: dict | None = None
    ) -> "BaseCollection":
        \"\"\"Create a new collection with optional metadata.\"\"\"
        raise NotImplementedError

    def move(self, xxx: "Xxx", to_collection: "BaseCollection", to_href: str) -> None:
        \"\"\"Atomically move an entry between collections.\"\"\"
        raise NotImplementedError

    def acquire_lock(self, mode: str) -> object:
        \"\"\"Acquire read/write lock (context manager).\"\"\"
        raise NotImplementedError
""",
        "function": "storage_interface_pluggable_backend",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "radicale/storage/__init__.py",
    },
    # ── 6. CalDAV filtering — recursive XML filter compiler ───────────────────
    {
        "normalized_code": """\
import xml.etree.ElementTree as ET
from typing import Optional, Tuple


def comp_match(
    xxx: "Xxx",
    filter_element: ET.Element,
    level: int = 0,
) -> Tuple[bool, bool]:
    \"\"\"Recursive CalDAV comp-filter evaluation.

    Levels: 0 = collection, 1 = component (VEVENT), 2 = sub-component (VALARM).
    Supports: comp-filter, prop-filter, time-range, is-not-defined.

    Returns:
        (matches, all_filters_satisfied)
    \"\"\"
    comp_name = filter_element.get("name", "")
    is_not_defined = filter_element.find("{DAV:}is-not-defined") is not None
    if level == 0:
        if xxx.component_name != comp_name:
            return is_not_defined, is_not_defined
    children = list(filter_element)
    if not children:
        return not is_not_defined, True
    all_match = True
    for child in children:
        child_name = child_element_name(child)
        if child_name == "comp-filter":
            match, _ = comp_match(xxx, child, level=level + 1)
        elif child_name == "prop-filter":
            match = prop_match(xxx, child)
        elif child_name == "time-range":
            match = time_range_match(xxx, child)
        else:
            match = True
        if not match:
            all_match = False
    return all_match != is_not_defined, all_match


def prop_match(xxx: "Xxx", filter_element: ET.Element) -> bool:
    \"\"\"Match a property filter (existence check, text-match, param-filter).\"\"\"
    prop_name = filter_element.get("name", "")
    is_not_defined = filter_element.find("{DAV:}is-not-defined") is not None
    has_prop = hasattr(xxx.vobject, prop_name.lower())
    if is_not_defined:
        return not has_prop
    return has_prop


def time_range_match(xxx: "Xxx", filter_element: ET.Element) -> bool:
    \"\"\"Check if entry time range overlaps with filter time range.\"\"\"
    start_str = filter_element.get("start")
    end_str = filter_element.get("end")
    filter_start = parse_utc_timestamp(start_str) if start_str else 0
    filter_end = parse_utc_timestamp(end_str) if end_str else float("inf")
    if xxx.time_range is None:
        return False
    entry_start, entry_end = xxx.time_range
    return entry_start < filter_end and entry_end > filter_start
""",
        "function": "caldav_recursive_xml_filter",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "radicale/item/filter.py",
    },
    # ── 7. WSGI app — mixin composition for HTTP methods ──────────────────────
    {
        "normalized_code": """\
from typing import Iterable


class ApplicationPartDelete:
    \"\"\"Handle WebDAV DELETE method.\"\"\"

    def do_DELETE(self, environ: dict, path: str) -> tuple[str, list, Iterable[bytes]]:
        raise NotImplementedError


class ApplicationPartGet:
    \"\"\"Handle WebDAV GET/HEAD method.\"\"\"

    def do_GET(self, environ: dict, path: str) -> tuple[str, list, Iterable[bytes]]:
        raise NotImplementedError


class ApplicationPartPut:
    \"\"\"Handle WebDAV PUT method (upload/replace entry).\"\"\"

    def do_PUT(self, environ: dict, path: str) -> tuple[str, list, Iterable[bytes]]:
        raise NotImplementedError


class ApplicationPartPropfind:
    \"\"\"Handle WebDAV PROPFIND method (discover collections + metadata).\"\"\"

    def do_PROPFIND(self, environ: dict, path: str) -> tuple[str, list, Iterable[bytes]]:
        raise NotImplementedError


class Application(
    ApplicationPartDelete,
    ApplicationPartGet,
    ApplicationPartPut,
    ApplicationPartPropfind,
):
    \"\"\"WSGI application — each HTTP method is a separate mixin.\"\"\"

    def __call__(
        self, environ: dict, start_response: callable,
    ) -> Iterable[bytes]:
        method = environ.get("REQUEST_METHOD", "GET").upper()
        handler = getattr(self, f"do_{method}", None)
        if handler is None:
            start_response("405 Method Not Allowed", [])
            return [b""]
        status, headers, body = handler(environ, path=environ.get("PATH_INFO", "/"))
        start_response(status, headers)
        return body
""",
        "function": "wsgi_mixin_method_dispatch",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "radicale/app/__init__.py",
    },
    # ── 8. XML namespace management + Clark notation ──────────────────────────
    {
        "normalized_code": """\
import xml.etree.ElementTree as ET


NAMESPACES: dict[str, str] = {
    "C": "urn:ietf:params:xml:ns:caldav",
    "CR": "urn:ietf:params:xml:ns:carddav",
    "D": "DAV:",
    "CS": "http://calendarserver.org/ns/",
    "ICAL": "http://apple.com/ns/ical/",
}

NAMESPACES_REV: dict[str, str] = {v: k for k, v in NAMESPACES.items()}


def make_clark(qualified_name: str) -> str:
    \"\"\"Convert prefixed name to Clark notation.

    Example: 'C:calendar' → '{urn:ietf:params:xml:ns:caldav}calendar'
    \"\"\"
    if ":" not in qualified_name:
        return qualified_name
    prefix, local = qualified_name.split(":", 1)
    ns = NAMESPACES.get(prefix, "")
    return f"{{{ns}}}{local}"


def make_human_readable(clark: str) -> str:
    \"\"\"Convert Clark notation back to human-readable.

    Example: '{urn:ietf:params:xml:ns:caldav}calendar' → 'C:calendar'
    \"\"\"
    if not clark.startswith("{"):
        return clark
    ns, local = clark[1:].split("}", 1)
    prefix = NAMESPACES_REV.get(ns, ns)
    return f"{prefix}:{local}"


def webdav_error(error_name: str) -> ET.Element:
    \"\"\"Create a WebDAV error XML element.\"\"\"
    error = ET.Element(make_clark("D:error"))
    ET.SubElement(error, make_clark(error_name))
    return error


# Register namespaces for automatic prefix in output
for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)
""",
        "function": "xml_namespace_clark_notation",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "radicale/xmlutils.py",
    },
    # ── 9. Declarative configuration schema with validators ───────────────────
    {
        "normalized_code": """\
import os
from collections import OrderedDict
from typing import Any, Callable


def positive_int(value: str) -> int:
    \"\"\"Validate positive integer config value.\"\"\"
    result = int(value)
    if result <= 0:
        raise ValueError(f"Expected positive integer, got {result}")
    return result


def filepath(value: str) -> str:
    \"\"\"Validate and expand file path.\"\"\"
    return os.path.expanduser(value)


DEFAULT_CONFIG_SCHEMA: OrderedDict[str, OrderedDict[str, dict[str, Any]]] = OrderedDict({
    "server": OrderedDict({
        "hosts": {"value": "localhost:5232", "type": str, "help": "Bind addresses"},
        "max_connections": {"value": "8", "type": positive_int, "help": "Max concurrent connections"},
        "ssl": {"value": "false", "type": bool, "help": "Enable SSL"},
    }),
    "auth": OrderedDict({
        "type": {
            "value": "none",
            "type": str,
            "help": "Authentication backend type",
            "internal": ("none", "htpasswd", "ldap", "imap", "oauth2"),
        },
        "delay": {"value": "1", "type": positive_int, "help": "Delay after failed login (seconds)"},
        "cache_logins": {"value": "true", "type": bool, "help": "Cache login results"},
    }),
    "storage": OrderedDict({
        "type": {"value": "multifilesystem", "type": str, "help": "Storage backend"},
        "filesystem_folder": {
            "value": "/var/lib/xxx/collections",
            "type": filepath,
            "help": "Storage directory",
        },
    }),
})


class XxxConfiguration:
    \"\"\"Hierarchical config with declarative schema + validators.

    Supports: multiple config files (? prefix = optional), plugin-specific overlays,
    and tracks which file set each value.
    \"\"\"

    def __init__(self, schema: dict | None = None) -> None:
        self._schema = schema or DEFAULT_CONFIG_SCHEMA
        self._values: dict[str, dict[str, Any]] = {}
        self._sources: dict[str, dict[str, str]] = {}

    def load(self, paths: str) -> None:
        \"\"\"Load config from compound path string ('?/etc/xxx:?~/.config/xxx').

        ? prefix means optional (skip if missing).
        \"\"\"
        for path in paths.split(":"):
            optional = path.startswith("?")
            if optional:
                path = path[1:]
            path = os.path.expanduser(path)
            if not os.path.exists(path):
                if optional:
                    continue
                raise FileNotFoundError(f"Config file not found: {path}")
            self._parse_file(path)

    def get(self, section: str, option: str) -> Any:
        \"\"\"Get a typed config value.\"\"\"
        if section in self._values and option in self._values[section]:
            return self._values[section][option]
        schema = self._schema.get(section, {}).get(option, {})
        raw = schema.get("value", "")
        type_fn: Callable = schema.get("type", str)
        return type_fn(raw)

    def get_source(self, section: str, option: str) -> str:
        \"\"\"Which config file set this value?\"\"\"
        return self._sources.get(section, {}).get(option, "default")
""",
        "function": "declarative_config_schema_validators",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "radicale/config.py",
    },
    # ── 10. HTTP utilities — path sanitization + gzip compression ─────────────
    {
        "normalized_code": """\
import gzip
import re
from typing import Iterable


def sanitize_path(path: str) -> str:
    \"\"\"Sanitize and normalize a URL path.

    Removes double slashes, ../ traversal, and leading/trailing whitespace.
    \"\"\"
    path = re.sub(r"/+", "/", path)
    parts = path.split("/")
    safe_parts: list[str] = []
    for part in parts:
        if part == "..":
            if safe_parts:
                safe_parts.pop()
        elif part and part != ".":
            safe_parts.append(part)
    return "/" + "/".join(safe_parts)


def compress_response(
    body: Iterable[bytes],
    accept_encoding: str,
) -> tuple[Iterable[bytes], dict[str, str]]:
    \"\"\"Optionally gzip-compress response body based on Accept-Encoding.\"\"\"
    headers: dict[str, str] = {}
    if "gzip" not in accept_encoding:
        return body, headers
    raw = b"".join(body)
    compressed = gzip.compress(raw)
    headers["Content-Encoding"] = "gzip"
    headers["Content-Length"] = str(len(compressed))
    return [compressed], headers
""",
        "function": "http_path_sanitize_gzip",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "radicale/httputils.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "authentication plugin registry configuration driven loading",
    "CalDAV iCalendar data model lazy loading with cache",
    "abstract storage interface pluggable backend collections",
    "recursive XML filter compiler CalDAV time-range",
    "WSGI application HTTP method dispatch mixin composition",
    "XML namespace Clark notation CalDAV CardDAV",
    "declarative configuration schema with validators",
    "permissions system character-based authorization",
    "HTTP path sanitization and gzip compression",
]


def clone_repo() -> None:
    import os
    if os.path.isdir(REPO_LOCAL):
        return
    subprocess.run(
        ["git", "clone", REPO_URL, REPO_LOCAL, "--depth=1"],
        check=True, capture_output=True,
    )


def build_payloads() -> list[dict]:
    payloads = []
    for p in PATTERNS:
        payloads.append(
            build_payload(
                normalized_code=p["normalized_code"],
                function=p["function"],
                feature_type=p["feature_type"],
                file_role=p["file_role"],
                language=LANGUAGE,
                framework=FRAMEWORK,
                stack=STACK,
                file_path=p["file_path"],
                source_repo=SOURCE_REPO,
                tag=TAG,
                charte_version=CHARTE_VERSION,
            )
        )
    return payloads


def index_patterns(client: QdrantClient, payloads: list[dict]) -> int:
    codes = [p["normalized_code"] for p in payloads]
    vectors = embed_documents_batch(codes)
    points = []
    for vec, payload in zip(vectors, payloads):
        points.append(PointStruct(id=make_uuid(), vector=vec, payload=payload))
    client.upsert(collection_name=COLLECTION, points=points)
    return len(points)


def run_audit_queries(client: QdrantClient) -> list[dict]:
    results = []
    for q in AUDIT_QUERIES:
        vec = embed_query(q)
        hits = query_kb(client, COLLECTION, query_vector=vec, language=LANGUAGE, limit=1)
        if hits:
            hit = hits[0]
            results.append({
                "query": q, "function": hit.payload.get("function", "?"),
                "file_role": hit.payload.get("file_role", "?"),
                "score": hit.score, "code_preview": hit.payload.get("normalized_code", "")[:50],
            })
        else:
            results.append({"query": q, "function": "NO_RESULT", "file_role": "?", "score": 0.0, "code_preview": ""})
    return results


def audit_normalization(client: QdrantClient) -> list[str]:
    violations = []
    scroll_result = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]),
        limit=100,
    )
    for point in scroll_result[0]:
        code = point.payload.get("normalized_code", "")
        fn = point.payload.get("function", "?")
        v = check_charte_violations(code, fn, language=LANGUAGE)
        violations.extend(v)
    return violations


def cleanup(client: QdrantClient) -> None:
    client.delete(
        collection_name=COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))])
        ),
    )


def main() -> None:
    print(f"\n{'='*60}")
    print(f"  INGESTION {REPO_NAME}")
    print(f"  Mode: {'DRY_RUN' if DRY_RUN else 'PRODUCTION'}")
    print(f"{'='*60}\n")

    client = QdrantClient(path=KB_PATH)
    count_initial = client.count(collection_name=COLLECTION).count
    print(f"  KB initial: {count_initial} points")

    clone_repo()

    payloads = build_payloads()
    print(f"  {len(PATTERNS)} patterns extraits")

    cleanup(client)

    n_indexed = index_patterns(client, payloads)
    count_after = client.count(collection_name=COLLECTION).count
    print(f"  {n_indexed} patterns indexés — KB: {count_after} points")

    query_results = run_audit_queries(client)
    violations = audit_normalization(client)

    report = audit_report(
        repo_name=REPO_NAME,
        dry_run=DRY_RUN,
        count_before=count_initial,
        count_after=count_after,
        patterns_extracted=len(PATTERNS),
        patterns_indexed=n_indexed,
        query_results=query_results,
        violations=violations,
    )
    print(report)

    if DRY_RUN:
        cleanup(client)
        print("  DRY_RUN — données supprimées")


if __name__ == "__main__":
    main()
