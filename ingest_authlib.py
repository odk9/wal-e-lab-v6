"""
ingest_authlib.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
d'authlib/authlib dans la KB Qdrant V6.

Focus : CORE patterns OAuth2/OIDC/JWT (authorization code flow, token generation,
JWT creation/validation, PKCE, refresh token rotation, bearer token validation,
OIDC discovery, token introspection, token revocation, session management).

Usage:
    .venv/bin/python3 ingest_authlib.py
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
REPO_URL = "https://github.com/authlib/authlib.git"
REPO_NAME = "authlib/authlib"
REPO_LOCAL = "/tmp/authlib"
LANGUAGE = "python"
FRAMEWORK = "generic"
STACK = "python+oauth2+jwt+oidc"
CHARTE_VERSION = "1.0"
TAG = "authlib/authlib"
SOURCE_REPO = "https://github.com/authlib/authlib"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Authlib = OAuth2/OIDC/JWT library.
# Patterns CORE : OAuth2 flows, JWT creation/validation, token management.
# U-5 : `client` est OK (OAuth terme), `token` est OK (auth terme),
#       `session` est OK, `grant` est OK, `scope` est OK.

PATTERNS: list[dict] = [
    # ── 1. OAuth2 Authorization Code Grant — Authorization Endpoint ───────────
    {
        "normalized_code": """\
import logging

from authlib.common.security import generate_token
from authlib.common.urls import add_params_to_uri

log = logging.getLogger(__name__)


def validate_authorization_request(self):
    \"\"\"Validate the authorization request from client.

    Per RFC 6749 Section 4.1.1 — extract and validate response_type,
    client_id, redirect_uri, scope, state.
    \"\"\"
    request = self.request
    response_type = request.response_type
    if response_type not in self.RESPONSE_TYPES:
        raise UnsupportedResponseTypeError()

    client = self.authenticate_client(request.client_id)
    if not client:
        raise InvalidClientError()

    if request.redirect_uri and not client.check_redirect_uri(request.redirect_uri):
        raise InvalidRequestError("Invalid redirect_uri")

    scope = request.scope
    if not client.check_scope(scope):
        raise InvalidScopeError()

    return client


def create_authorization_response(self, client):
    \"\"\"Create authorization response with code or token.\"\"\"
    code = generate_token(self.AUTHORIZATION_CODE_LENGTH)
    redirect_uri = self.request.redirect_uri or client.default_redirect_uri

    self.save_authorization_code(code, client, self.request)

    params = {"code": code}
    if self.request.state:
        params["state"] = self.request.state

    return redirect_uri, params
""",
        "function": "oauth2_authorization_code_grant_endpoint",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "authlib/oauth2/rfc6749/grants/authorization_code.py",
    },
    # ── 2. OAuth2 Token Endpoint — Access Token Generation ─────────────────
    {
        "normalized_code": """\
from typing import Optional


class BearerTokenGenerator:
    \"\"\"Generate bearer token response for OAuth2 token endpoint.\"\"\"

    DEFAULT_EXPIRES_IN = 3600
    GRANT_TYPES_EXPIRES_IN = {
        "authorization_code": 864000,
        "implicit": 3600,
        "password": 864000,
        "client_credentials": 864000,
    }

    def __init__(
        self,
        access_token_generator,
        refresh_token_generator: Optional[callable] = None,
        expires_generator: Optional[callable] = None,
    ):
        self.access_token_generator = access_token_generator
        self.refresh_token_generator = refresh_token_generator
        self.expires_generator = expires_generator

    def _get_expires_in(self, client, grant_type: str) -> int:
        \"\"\"Get expires_in value for token.\"\"\"
        if self.expires_generator is None:
            expires_in = self.GRANT_TYPES_EXPIRES_IN.get(
                grant_type, self.DEFAULT_EXPIRES_IN
            )
        elif callable(self.expires_generator):
            expires_in = self.expires_generator(client, grant_type)
        else:
            expires_in = self.DEFAULT_EXPIRES_IN
        return expires_in

    def generate_token(
        self,
        grant_type: str,
        client,
        include_refresh_token: bool = True,
    ) -> dict:
        \"\"\"Generate token dict with access_token, refresh_token, expires_in.\"\"\"
        expires_in = self._get_expires_in(client, grant_type)
        access_token = self.access_token_generator(client, grant_type)
        token = {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": expires_in,
        }
        if include_refresh_token and self.refresh_token_generator:
            token["refresh_token"] = self.refresh_token_generator(client, grant_type)
        return token
""",
        "function": "oauth2_bearer_token_generator",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "authlib/oauth2/rfc6750/token.py",
    },
    # ── 3. JWT Creation and Encoding ─────────────────────────────────────────
    {
        "normalized_code": """\
import calendar
import datetime
from typing import Optional

from authlib.common.encoding import json_dumps, to_bytes


class JsonWebToken:
    \"\"\"Create and validate JSON Web Tokens (JWT).\"\"\"

    SENSITIVE_NAMES = ("password", "token", "secret", "secret_key")

    def __init__(self, algorithms: list[str], private_headers: Optional[dict] = None):
        self._jws = JsonWebSignature(algorithms, private_headers=private_headers)
        self._jwe = JsonWebEncryption(algorithms, private_headers=private_headers)

    def check_sensitive_data(self, payload: dict) -> None:
        \"\"\"Validate payload does not contain sensitive information.\"\"\"
        for k in payload:
            if k in self.SENSITIVE_NAMES:
                raise InsecureClaimError(k)

    def encode(
        self,
        header: dict,
        payload: dict,
        key,
        check: bool = True,
    ) -> bytes:
        \"\"\"Encode JWT with header, payload, and key.

        Converts datetime claims to timestamps, checks sensitive data,
        signs with JWS or encrypts with JWE if 'enc' header present.
        \"\"\"
        header.setdefault("typ", "JWT")

        for k in ["exp", "iat", "nbf"]:
            claim = payload.get(k)
            if isinstance(claim, datetime.datetime):
                payload[k] = calendar.timegm(claim.utctimetuple())

        if check:
            self.check_sensitive_data(payload)

        key = find_encode_key(key, header)
        text = to_bytes(json_dumps(payload))

        if "enc" in header:
            return self._jwe.serialize_compact(header, text, key)
        else:
            return self._jws.serialize_compact(header, text, key)
""",
        "function": "jwt_encode_with_signature_encryption",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "authlib/jose/rfc7519/jwt.py",
    },
    # ── 4. PKCE (Proof Key for Code Exchange) — S256 Challenge ──────────────
    {
        "normalized_code": """\
import hashlib
import re

from authlib.common.encoding import to_bytes, to_unicode, urlsafe_b64encode


CODE_VERIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9\\-._~]{43,128}$")


def create_s256_code_challenge(code_verifier: str) -> str:
    \"\"\"Create S256 code_challenge from code_verifier via SHA256.\"\"\"
    data = hashlib.sha256(to_bytes(code_verifier, "ascii")).digest()
    return to_unicode(urlsafe_b64encode(data))


def compare_s256_code_challenge(code_verifier: str, code_challenge: str) -> bool:
    \"\"\"Verify code_verifier matches S256 code_challenge.\"\"\"
    return create_s256_code_challenge(code_verifier) == code_challenge


class CodeChallenge:
    \"\"\"PKCE extension for Authorization Code Grant (RFC 7636).

    Improves security for public clients by requiring code_challenge
    and code_verifier in authorization and token requests.
    \"\"\"

    SUPPORTED_CODE_CHALLENGE_METHOD = ["plain", "S256"]
    CODE_CHALLENGE_METHODS = {
        "plain": lambda v, c: v == c,
        "S256": compare_s256_code_challenge,
    }

    def __init__(self, required: bool = True):
        self.required = required

    def validate_code_challenge(self, code_challenge: str) -> None:
        \"\"\"Validate code_challenge format.\"\"\"
        if not CODE_VERIFIER_PATTERN.match(code_challenge):
            raise InvalidRequestError("Invalid code_challenge format")
""",
        "function": "pkce_s256_code_challenge_validation",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "authlib/oauth2/rfc7636/challenge.py",
    },
    # ── 5. Refresh Token Grant — Token Rotation ──────────────────────────────
    {
        "normalized_code": """\
import logging

from authlib.oauth2.rfc6749 import InvalidGrantError

log = logging.getLogger(__name__)


class RefreshTokenGrant:
    \"\"\"Refresh Token Grant (RFC 6749 Section 6).

    Allows client to obtain new access_token using refresh_token.
    Supports optional new refresh_token issuance.
    \"\"\"

    GRANT_TYPE = "refresh_token"
    INCLUDE_NEW_REFRESH_TOKEN = False

    def _validate_request_client(self):
        \"\"\"Authenticate client and verify grant_type authorization.\"\"\"
        client = self.authenticate_token_endpoint_client()
        log.debug("Validate token request of %r", client)

        if not client.check_grant_type(self.GRANT_TYPE):
            raise UnauthorizedClientError(
                f"The client is not authorized to use 'grant_type={self.GRANT_TYPE}'"
            )
        return client

    def _validate_request_token(self, client):
        \"\"\"Extract and validate refresh_token from request.\"\"\"
        refresh_token = self.request.form.get("refresh_token")
        if refresh_token is None:
            raise InvalidRequestError("Missing 'refresh_token' in request.")

        token = self.authenticate_refresh_token(refresh_token)
        if not token or not token.check_client(client):
            raise InvalidGrantError()
        return token

    def process_request(self, request):
        \"\"\"Main entry point: validate request, generate new token.\"\"\"
        client = self._validate_request_client()
        old_token = self._validate_request_token(client)

        new_token = self.generate_token(client)
        if self.INCLUDE_NEW_REFRESH_TOKEN:
            new_token["refresh_token"] = self.generate_refresh_token(client)

        self.save_token(new_token, request)
        return new_token
""",
        "function": "oauth2_refresh_token_grant_rotation",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "authlib/oauth2/rfc6749/grants/refresh_token.py",
    },
    # ── 6. Bearer Token Validation (RFC 6750) ────────────────────────────────
    {
        "normalized_code": """\
from typing import Optional


class BearerTokenValidator:
    \"\"\"Validate Bearer token in HTTP Authorization header.

    Per RFC 6750 Section 2.1 — extract token from 'Bearer <token>' header
    and validate with scope requirements.
    \"\"\"

    def __init__(self, realm: Optional[str] = None):
        self.realm = realm

    def authenticate_token(self, token_string: str) -> dict:
        \"\"\"Look up token by token_string in database.

        Subclasses MUST implement this to query token storage.
        \"\"\"
        raise NotImplementedError()

    def validate_token(self, token: dict, scopes: list[str], request):
        \"\"\"Validate token is active and has required scopes.\"\"\"
        if not token or not token.get("active", True):
            raise InvalidTokenError(realm=self.realm)

        token_scopes = token.get("scope", "").split()
        if scopes and not set(scopes).issubset(set(token_scopes)):
            raise InsufficientScopeError()

    def parse_request_authorization(self, request) -> Optional[str]:
        \"\"\"Extract Bearer token from Authorization header.\"\"\"
        auth = request.headers.get("Authorization", "")
        try:
            auth_type, token_string = auth.split(None, 1)
        except ValueError:
            return None

        if auth_type.lower() != "bearer":
            return None
        return token_string
""",
        "function": "bearer_token_validator_rfc6750",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "authlib/oauth2/rfc6750/validator.py",
    },
    # ── 7. Token Introspection (RFC 7662) ───────────────────────────────────
    {
        "normalized_code": """\
from typing import Optional


class IntrospectTokenValidator:
    \"\"\"Token validator via introspection endpoint (RFC 7662).

    Validates token by querying remote authorization server's
    introspection endpoint instead of local validation.
    \"\"\"

    TOKEN_TYPE = "bearer"

    def introspect_token(self, token_string: str) -> dict:
        \"\"\"Request introspection endpoint and return token info.

        Subclasses MUST implement this. Example:

            def introspect_token(self, token_string: str):
                url = "https://auth.example.com/oauth/introspect"
                resp = requests.post(url, data={"token": token_string})
                return resp.json()
        \"\"\"
        raise NotImplementedError()

    def authenticate_token(self, token_string: str) -> dict:
        \"\"\"Authenticate token via introspection endpoint.\"\"\"
        return self.introspect_token(token_string)

    def validate_token(self, token: dict, scopes: list[str], request):
        \"\"\"Validate introspected token is active with required scopes.\"\"\"
        if not token or not token.get("active", False):
            raise InvalidTokenError(realm=self.realm)

        token_scopes = token.get("scope", "").split()
        if scopes and not set(scopes).issubset(set(token_scopes)):
            raise InsufficientScopeError()
""",
        "function": "token_introspection_validator_rfc7662",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "authlib/oauth2/rfc7662/token_validator.py",
    },
    # ── 8. Token Revocation Endpoint (RFC 7009) ────────────────────────────
    {
        "normalized_code": """\
from typing import Optional


class RevocationEndpoint:
    \"\"\"Token revocation endpoint (RFC 7009).

    Allows resource owners and clients to revoke tokens (access_token
    or refresh_token) when no longer needed.
    \"\"\"

    ENDPOINT_NAME = "revocation"
    SUPPORTED_TOKEN_TYPES = ["access_token", "refresh_token"]

    def authenticate_token(self, request, client) -> Optional[dict]:
        \"\"\"Extract and validate token from revocation request.

        Per RFC 7009 Section 2 — extract 'token' parameter and
        optional 'token_type_hint'.
        \"\"\"
        self.check_params(request, client)
        token = self.query_token(
            request.form["token"],
            request.form.get("token_type_hint")
        )
        if token and not token.check_client(client):
            raise InvalidGrantError()
        return token

    def check_params(self, request, client) -> None:
        \"\"\"Validate revocation request parameters.\"\"\"
        if "token" not in request.form:
            raise InvalidRequestError("Missing 'token' parameter")

        hint = request.form.get("token_type_hint")
        if hint and hint not in self.SUPPORTED_TOKEN_TYPES:
            raise UnsupportedTokenTypeError()

    def revoke_token(self, token: dict, request):
        \"\"\"Revoke the token in database (mark inactive or delete).\"\"\"
        raise NotImplementedError()

    def create_endpoint_response(self, request, client):
        \"\"\"Process revocation request and return 200 OK response.\"\"\"
        token = self.authenticate_token(request, client)
        if token:
            self.revoke_token(token, request)
        return 200, ""
""",
        "function": "token_revocation_endpoint_rfc7009",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "authlib/oauth2/rfc7009/revocation.py",
    },
    # ── 9. OpenID Connect Discovery (RFC 8414) ──────────────────────────────
    {
        "normalized_code": """\
from typing import Optional


def get_well_known_url(
    issuer: str,
    external: bool = False,
    suffix: str = "oauth-authorization-server",
) -> str:
    \"\"\"Get well-known discovery URI for OAuth2/OIDC metadata.

    Per RFC 8414 Section 3.1 — construct .well-known URI from issuer.
    For OIDC, use suffix='openid-configuration'.
    \"\"\"
    from authlib.common.urls import urlparse

    parsed = urlparse.urlparse(issuer)
    path = parsed.path

    if path and path != "/":
        url_path = f"/.well-known/{suffix}{path}"
    else:
        url_path = f"/.well-known/{suffix}"

    if not external:
        return url_path
    return parsed.scheme + "://" + parsed.netloc + url_path


class WellKnownEndpoint:
    \"\"\"Publish OAuth2/OIDC server metadata at /.well-known/.

    Allows clients to discover authorization_endpoint, token_endpoint,
    userinfo_endpoint, jwks_uri, and other capabilities.
    \"\"\"

    def __init__(self, issuer: str, claims: dict):
        self.issuer = issuer
        self.claims = claims

    def get_metadata(self) -> dict:
        \"\"\"Return server metadata dict.\"\"\"
        metadata = self.claims.copy()
        metadata["issuer"] = self.issuer
        return metadata

    def create_endpoint_response(self, request):
        \"\"\"HTTP endpoint handler — return metadata as JSON.\"\"\"
        metadata = self.get_metadata()
        return 200, metadata
""",
        "function": "oidc_discovery_well_known_endpoint",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "authlib/oauth2/rfc8414/well_known.py",
    },
    # ── 10. OpenID Connect ID Token Validation ───────────────────────────────
    {
        "normalized_code": """\
from typing import Optional

from joserfc import jwt
from joserfc.jwk import KeySet


class OpenIDMixin:
    \"\"\"OpenID Connect client helpers — JWK set, profile, ID token validation.\"\"\"

    def fetch_jwk_set(self, force: bool = False) -> dict:
        \"\"\"Fetch JWKS (public keys) from authorization server.\"\"\"
        metadata = self.load_server_metadata()
        jwk_set = metadata.get("jwks")

        if jwk_set and not force:
            return jwk_set

        uri = metadata.get("jwks_uri")
        if not uri:
            raise RuntimeError('Missing "jwks_uri" in server metadata')

        with self._get_session() as session:
            resp = session.request("GET", uri, withhold_token=True)
            resp.raise_for_status()
            jwk_set = resp.json()

        self.server_metadata["jwks"] = jwk_set
        return jwk_set

    def parse_id_token(
        self,
        token: dict,
        nonce: str,
        claims_options: Optional[dict] = None,
        claims_cls: Optional[type] = None,
        leeway: int = 120,
    ):
        \"\"\"Validate and parse ID token from token response.\"\"\"
        if "id_token" not in token:
            return None

        claims_params = dict(
            nonce=nonce,
            client_id=self.client_id,
        )

        if claims_cls is None:
            if "access_token" in token:
                claims_params["access_token"] = token["access_token"]
                claims_cls = CodeIDToken
            else:
                claims_cls = ImplicitIDToken

        metadata = self.load_server_metadata()
        if claims_options is None and "issuer" in metadata:
            claims_options = {"iss": {"values": [metadata["issuer"]]}}

        return jwt.decode(
            token["id_token"],
            self.fetch_jwk_set(),
            claims_cls=claims_cls,
            claims_options=claims_options,
            claims_params=claims_params,
            leeway=leeway,
        )

    def fetch_profile(self, **kwargs):
        \"\"\"Fetch profile (userinfo) from profile_endpoint.\"\"\"
        metadata = self.load_server_metadata()
        resp = self.get(metadata["userinfo_endpoint"], **kwargs)
        resp.raise_for_status()
        return resp.json()
""",
        "function": "openid_connect_id_token_userinfo",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "authlib/integrations/base_client/sync_openid.py",
    },
    # ── 11. OAuth2 Authorization Server Setup ──────────────────────────────
    {
        "normalized_code": """\
from typing import Callable, Optional


class AuthorizationServer:
    \"\"\"Authorization server handling both authorization and token endpoints.

    Manages multiple OAuth2 grant types (authorization_code, refresh_token,
    client_credentials, etc.) and token generators.
    \"\"\"

    def __init__(self, scopes_supported: Optional[list[str]] = None):
        self.scopes_supported = scopes_supported or []
        self._token_generators = {}
        self._client_auth = None
        self._authorization_grants = []
        self._token_grants = []
        self._endpoints = {}

    def query_client(self, client_id: str):
        \"\"\"Load OAuth client by client_id from database.

        Subclasses MUST implement — return object with ClientMixin interface.
        \"\"\"
        raise NotImplementedError()

    def save_token(self, token: dict, request):
        \"\"\"Save generated token to database.

        Subclasses MUST implement — store access_token, refresh_token,
        expires_in for later validation.
        \"\"\"
        raise NotImplementedError()

    def register_token_generator(
        self,
        grant_type: str,
        func: Callable,
    ) -> None:
        \"\"\"Register token generator for grant_type.

        Example:
            def generate_bearer_token(grant_type, client, subject=None, scope=None):
                return {
                    "access_token": generate_token(),
                    "token_type": "Bearer",
                    "expires_in": 3600,
                }
            server.register_token_generator("default", generate_bearer_token)
        \"\"\"
        self._token_generators[grant_type] = func

    def register_grant(self, grant_class, extensions: Optional[list] = None) -> None:
        \"\"\"Register OAuth2 grant type (AuthorizationCodeGrant, RefreshTokenGrant, etc).\"\"\"
        grant = grant_class(self)
        if extensions:
            for ext in extensions:
                grant.register_hook(ext)
        self._token_grants.append(grant)
""",
        "function": "oauth2_authorization_server_setup",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "authlib/oauth2/rfc6749/authorization_server.py",
    },
    # ── 12. Client Authentication Methods ───────────────────────────────────
    {
        "normalized_code": """\
from typing import Optional


class ClientAuthentication:
    \"\"\"Authenticate OAuth2 client via multiple auth methods.

    Per RFC 6749 Section 2.3 — supports client_secret_basic,
    client_secret_post, client_secret_jwt, private_key_jwt, etc.
    \"\"\"

    METHODS = {
        "client_secret_basic": authenticate_via_basic_auth,
        "client_secret_post": authenticate_via_post_body,
        "client_secret_jwt": authenticate_via_client_secret_jwt,
        "private_key_jwt": authenticate_via_private_key_jwt,
    }

    def authenticate_client(self, request, method: Optional[str] = None):
        \"\"\"Authenticate client from request using specified method.\"\"\"
        if not method:
            method = self.get_auth_method(request)

        if method not in self.METHODS:
            raise InvalidClientError(f"Unsupported auth method: {method}")

        client_id = self.METHODS[method](request)
        if not client_id:
            raise InvalidClientError()

        return self.query_client(client_id)

    def get_auth_method(self, request) -> str:
        \"\"\"Detect auth method from request headers and body.\"\"\"
        if request.headers.get("Authorization", "").startswith("Basic "):
            return "client_secret_basic"
        if "client_assertion" in request.form:
            return "client_secret_jwt"
        if "client_id" in request.form and "client_secret" in request.form:
            return "client_secret_post"
        raise InvalidClientError("No client authentication found")

    def query_client(self, client_id: str):
        \"\"\"Load client from database.\"\"\"
        raise NotImplementedError()
""",
        "function": "oauth2_client_authentication_methods",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "authlib/oauth2/rfc6749/authenticate_client.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "OAuth2 authorization code grant flow endpoint",
    "bearer token generator token response",
    "JWT create encode with JWS signature",
    "PKCE S256 code challenge verification",
    "OAuth2 refresh token rotation grant",
    "bearer token validator RFC 6750",
    "token introspection remote validation",
    "token revocation endpoint RFC 7009",
    "OpenID Connect discovery well-known metadata",
    "OpenID Connect ID token validation userinfo",
    "OAuth2 authorization server setup and grants",
    "OAuth2 client authentication methods",
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
                "query": q,
                "function": hit.payload.get("function", "?"),
                "file_role": hit.payload.get("file_role", "?"),
                "score": hit.score,
                "code_preview": hit.payload.get("normalized_code", "")[:50],
                "norm_ok": True,
            })
        else:
            results.append({"query": q, "function": "NO_RESULT", "file_role": "?", "score": 0.0, "code_preview": "", "norm_ok": False})
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

    # Cleanup existing points for this tag
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
