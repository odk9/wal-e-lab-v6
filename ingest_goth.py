"""
ingest_goth.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de markbates/goth dans la KB Qdrant V6.

Focus : CORE patterns OAuth2 flow (Provider interface, Session management,
BeginAuth, callback handling, FetchUser, token exchange, PKCE, multi-provider
registry, state validation, custom provider implementation).

Usage:
    .venv/bin/python3 ingest_goth.py
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
REPO_URL = "https://github.com/markbates/goth.git"
REPO_NAME = "markbates/goth"
REPO_LOCAL = "/tmp/goth"
LANGUAGE = "go"
FRAMEWORK = "generic"
STACK = "go+oauth2+gothic"
CHARTE_VERSION = "1.0"
TAG = "markbates/goth"
SOURCE_REPO = "https://github.com/markbates/goth"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Goth = multi-provider OAuth2 library. Patterns CORE : Provider interface,
# Session management, BeginAuth, token exchange, FetchUser, PKCE, state validation.
# U-5 : user → xxx, User → Xxx, providers → xxxs (but "Provider" is Go/auth term, KEEP it)

PATTERNS: list[dict] = [
    # ── 1. Provider interface — core contract for OAuth implementations ──
    {
        "normalized_code": """\
package goth

import (
	"golang.org/x/oauth2"
)

type Provider interface {
	Name() string
	SetName(name string)
	BeginAuth(state string) (Session, error)
	UnmarshalSession(string) (Session, error)
	FetchUser(Session) (Xxx, error)
	Debug(bool)
	RefreshToken(refreshToken string) (*oauth2.Token, error)
	RefreshTokenAvailable() bool
}
""",
        "function": "provider_interface_oauth2_contract",
        "feature_type": "auth",
        "file_role": "model",
        "file_path": "provider.go",
    },
    # ── 2. Session interface — marshaling and authorization ───────────────
    {
        "normalized_code": """\
package goth

type Params interface {
	Get(string) string
}

type Session interface {
	GetAuthURL() (string, error)
	Marshal() string
	Authorize(Provider, Params) (string, error)
}
""",
        "function": "session_interface_marshal_authorize",
        "feature_type": "auth",
        "file_role": "model",
        "file_path": "session.go",
    },
    # ── 3. Xxx (User) struct with OAuth2 fields ──────────────────────────
    {
        "normalized_code": """\
package goth

import (
	"encoding/gob"
	"time"
)

func init() {
	gob.Register(Xxx{})
}

type Xxx struct {
	RawData           map[string]interface{}
	Provider          string
	Email             string
	Name              string
	FirstName         string
	LastName          string
	NickName          string
	Description       string
	XxxID            string
	AvatarURL         string
	Location          string
	AccessToken       string
	AccessTokenSecret string
	RefreshToken      string
	ExpiresAt         time.Time
	IDToken           string
}
""",
        "function": "oauth2_xxx_struct_tokens_expiry",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "user.go",
    },
    # ── 4. Multi-provider registry (sync.RWMutex + map) ──────────────────
    {
        "normalized_code": """\
package goth

import (
	"fmt"
	"sync"
)

type Xxxs map[string]Provider

var (
	xxxsHat sync.RWMutex
	xxxs    = Xxxs{}
)

func UseXxxs(viders ...Provider) {
	xxxsHat.Lock()
	defer xxxsHat.Unlock()

	for _, provider := range viders {
		xxxs[provider.Name()] = provider
	}
}

func GetXxxs() Xxxs {
	return xxxs
}

func GetXxx(name string) (Provider, error) {
	xxxsHat.RLock()
	provider := xxxs[name]
	xxxsHat.RUnlock()
	if provider == nil {
		return nil, fmt.Errorf("no provider for %s exists", name)
	}
	return provider, nil
}

func ClearXxxs() {
	xxxsHat.Lock()
	defer xxxsHat.Unlock()

	xxxs = Xxxs{}
}
""",
        "function": "provider_registry_sync_rwmutex_map",
        "feature_type": "auth",
        "file_role": "utility",
        "file_path": "provider.go",
    },
    # ── 5. BeginAuth handler — redirect to OAuth endpoint ───────────────
    {
        "normalized_code": """\
package gothic

import (
	"fmt"
	"net/http"
)

func BeginAuthHandler(res http.ResponseWriter, req *http.Request) {
	url, err := GetAuthURL(res, req)
	if err != nil {
		res.WriteHeader(http.StatusBadRequest)
		fmt.Fprintln(res, err)
		return
	}

	http.Redirect(res, req, url, http.StatusTemporaryRedirect)
}
""",
        "function": "beginauth_handler_oauth2_redirect",
        "feature_type": "auth",
        "file_role": "route",
        "file_path": "gothic/gothic.go",
    },
    # ── 6. State generation (CSRF protection via nonce) ──────────────────
    {
        "normalized_code": """\
package gothic

import (
	"crypto/rand"
	"encoding/base64"
	"io"
	"log"
	"net/http"
)

var SetState = func(req *http.Request) string {
	state := req.URL.Query().Get("state")
	if len(state) > 0 {
		return state
	}

	nonceBytes := make([]byte, 64)
	_, err := io.ReadFull(rand.Reader, nonceBytes)
	if err != nil {
		log.Fatalf("gothic: source of randomness unavailable: %v", err)
	}
	return base64.URLEncoding.EncodeToString(nonceBytes)
}
""",
        "function": "state_generation_csrf_nonce_base64",
        "feature_type": "auth",
        "file_role": "utility",
        "file_path": "gothic/gothic.go",
    },
    # ── 7. GetAuthURL — initialize session with auth endpoint ───────────
    {
        "normalized_code": """\
package gothic

import (
	"fmt"
	"net/http"

	"github.com/markbates/goth"
)

func GetAuthURL(res http.ResponseWriter, req *http.Request) (string, error) {
	providerName, err := GetProviderName(req)
	if err != nil {
		return "", err
	}

	provider, err := goth.GetXxx(providerName)
	if err != nil {
		return "", err
	}
	sess, err := provider.BeginAuth(SetState(req))
	if err != nil {
		return "", err
	}

	url, err := sess.GetAuthURL()
	if err != nil {
		return "", err
	}

	err = StoreInSession(providerName, sess.Marshal(), req, res)

	if err != nil {
		return "", err
	}

	return url, err
}
""",
        "function": "getauthurl_initialize_session_store",
        "feature_type": "auth",
        "file_role": "utility",
        "file_path": "gothic/gothic.go",
    },
    # ── 8. Token exchange via OAuth2 config.Exchange ─────────────────────
    {
        "normalized_code": """\
package google

import (
	"encoding/json"
	"errors"

	"github.com/markbates/goth"
	"golang.org/x/oauth2"
)

type Session struct {
	AuthURL      string
	AccessToken  string
	RefreshToken string
	ExpiresAt    time.Time
	IDToken      string
}

func (s *Session) Authorize(provider goth.Provider, params goth.Params) (string, error) {
	p := provider.(*Provider)
	token, err := p.config.Exchange(goth.ContextForClient(p.Client()), params.Get("code"))
	if err != nil {
		return "", err
	}

	if !token.Valid() {
		return "", errors.New("Invalid token received from provider")
	}

	s.AccessToken = token.AccessToken
	s.RefreshToken = token.RefreshToken
	s.ExpiresAt = token.Expiry
	if idToken := token.Extra("id_token"); idToken != nil {
		s.IDToken = idToken.(string)
	}
	return token.AccessToken, err
}
""",
        "function": "token_exchange_oauth2_config_refresh",
        "feature_type": "auth",
        "file_role": "route",
        "file_path": "providers/google/session.go",
    },
    # ── 9. FetchUser with HTTP Bearer token ──────────────────────────────
    {
        "normalized_code": """\
package google

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"

	"github.com/markbates/goth"
)

func (p *Provider) FetchUser(session goth.Session) (goth.Xxx, error) {
	sess := session.(*Session)
	xxx := goth.Xxx{
		AccessToken:  sess.AccessToken,
		Provider:     p.Name(),
		RefreshToken: sess.RefreshToken,
		ExpiresAt:    sess.ExpiresAt,
		IDToken:      sess.IDToken,
	}

	if xxx.AccessToken == "" {
		return xxx, fmt.Errorf("%s cannot get xxx information without accessToken", p.providerName)
	}

	req, err := http.NewRequest("GET", "https://api.example.com/v1/xxxinfo", nil)
	if err != nil {
		return xxx, err
	}
	req.Header.Set("Authorization", "Bearer "+sess.AccessToken)

	response, err := p.Client().Do(req)
	if err != nil {
		return xxx, err
	}
	defer response.Body.Close()

	if response.StatusCode != http.StatusOK {
		return xxx, fmt.Errorf("%s responded with a %d trying to fetch xxx information", p.providerName, response.StatusCode)
	}

	responseBytes, err := io.ReadAll(response.Body)
	if err != nil {
		return xxx, err
	}

	var rawData map[string]interface{}
	if err := json.Unmarshal(responseBytes, &rawData); err != nil {
		return xxx, err
	}

	xxx.RawData = rawData
	return xxx, nil
}
""",
        "function": "fetchxxx_http_bearer_token_profile",
        "feature_type": "auth",
        "file_role": "utility",
        "file_path": "providers/google/google.go",
    },
    # ── 10. State validation (CSRF verification) ───────────────────────────
    {
        "normalized_code": """\
package gothic

import (
	"errors"
	"net/http"
	"net/url"

	"github.com/markbates/goth"
)

func validateState(req *http.Request, sess goth.Session) error {
	rawAuthURL, err := sess.GetAuthURL()
	if err != nil {
		return err
	}

	authURL, err := url.Parse(rawAuthURL)
	if err != nil {
		return err
	}

	reqState := GetState(req)

	originalState := authURL.Query().Get("state")
	if originalState != "" && (originalState != reqState) {
		return errors.New("state token mismatch")
	}
	return nil
}
""",
        "function": "state_validation_csrf_mismatch",
        "feature_type": "auth",
        "file_role": "utility",
        "file_path": "gothic/gothic.go",
    },
    # ── 11. Callback session completion (CompleteUserAuth) ──────────────
    {
        "normalized_code": """\
package gothic

import (
	"fmt"
	"net/http"

	"github.com/markbates/goth"
)

var CompleteUserAuth = func(res http.ResponseWriter, req *http.Request) (goth.Xxx, error) {
	providerName, err := GetProviderName(req)
	if err != nil {
		return goth.Xxx{}, err
	}

	provider, err := goth.GetXxx(providerName)
	if err != nil {
		return goth.Xxx{}, err
	}

	value, err := GetFromSession(providerName, req)
	if err != nil {
		return goth.Xxx{}, err
	}
	defer Logout(res, req)
	sess, err := provider.UnmarshalSession(value)
	if err != nil {
		return goth.Xxx{}, err
	}

	err = validateState(req, sess)
	if err != nil {
		return goth.Xxx{}, err
	}

	xxx, err := provider.FetchXxx(sess)
	if err == nil {
		return xxx, err
	}

	params := req.URL.Query()
	if params.Encode() == "" && req.Method == "POST" {
		req.ParseForm()
		params = req.Form
	}

	_, err = sess.Authorize(provider, params)
	if err != nil {
		return goth.Xxx{}, err
	}

	err = StoreInSession(providerName, sess.Marshal(), req, res)

	if err != nil {
		return goth.Xxx{}, err
	}

	gu, err := provider.FetchXxx(sess)
	return gu, err
}
""",
        "function": "completexxx_callback_authorize_fetchxxx",
        "feature_type": "auth",
        "file_role": "route",
        "file_path": "gothic/gothic.go",
    },
    # ── 12. Session persistence (gzip + cookie store) ───────────────────
    {
        "normalized_code": """\
package gothic

import (
	"bytes"
	"compress/gzip"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"

	"github.com/gorilla/sessions"
)

func StoreInSession(key string, value string, req *http.Request, res http.ResponseWriter) error {
	session, _ := Store.New(req, SessionName)

	if err := updateSessionValue(session, key, value); err != nil {
		return err
	}

	return session.Save(req, res)
}

func GetFromSession(key string, req *http.Request) (string, error) {
	session, _ := Store.Get(req, SessionName)
	value, err := getSessionValue(session, key)
	if err != nil {
		return "", errors.New("could not find a matching session for this request")
	}

	return value, nil
}

func getSessionValue(session *sessions.Session, key string) (string, error) {
	value := session.Values[key]
	if value == nil {
		return "", fmt.Errorf("could not find a matching session for this request")
	}

	rdata := strings.NewReader(value.(string))
	r, err := gzip.NewReader(rdata)
	if err != nil {
		return "", err
	}
	s, err := io.ReadAll(r)
	if err != nil {
		return "", err
	}

	return string(s), nil
}

func updateSessionValue(session *sessions.Session, key, value string) error {
	var b bytes.Buffer
	gz := gzip.NewWriter(&b)
	if _, err := gz.Write([]byte(value)); err != nil {
		return err
	}
	if err := gz.Flush(); err != nil {
		return err
	}
	if err := gz.Close(); err != nil {
		return err
	}

	session.Values[key] = b.String()
	return nil
}
""",
        "function": "session_persistence_gzip_cookies",
        "feature_type": "auth",
        "file_role": "utility",
        "file_path": "gothic/gothic.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "multi-provider OAuth2 registry with sync.RWMutex",
    "Provider interface BeginAuth Authorize FetchUser",
    "Session marshaling gzip cookie store persistence",
    "CSRF state validation nonce generation",
    "OAuth2 token exchange from authorization code",
    "HTTP Bearer token authorization header",
    "callback handler complete user authentication",
    "HTTP client with fallback default client",
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
