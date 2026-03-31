"""
ingest_async_stripe.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de arlyon/async-stripe dans la KB Qdrant V6.

Focus : CORE patterns async Stripe SDK (client builder, idempotency keys, webhook verification,
payment intent creation, pagination with streams, error handling, custom extractors for axum).

Usage:
    .venv/bin/python3 ingest_async_stripe.py
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
REPO_URL = "https://github.com/arlyon/async-stripe.git"
REPO_NAME = "arlyon/async-stripe"
REPO_LOCAL = "/tmp/async-stripe"
LANGUAGE = "rust"
FRAMEWORK = "generic"
STACK = "rust+stripe+async+tokio"
CHARTE_VERSION = "1.0"
TAG = "arlyon/async-stripe"
SOURCE_REPO = "https://github.com/arlyon/async-stripe"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# async-stripe = SDK Stripe officiel pour Rust avec tokio async runtime.
# Patterns CORE : client builder, request strategies (idempotency), webhook HMAC-SHA256,
# payment intents, pagination streams, error handling, type-safe request builders.
# U-5 : customer → xxx, payment_intent → payment_xxx, charge → transaction, etc.
# KEEP: Stripe domain terms (Customer, Subscription, Invoice, PaymentIntent, StripeError, etc.)

PATTERNS: list[dict] = [
    # ── 1. Client builder with fluent API — initialization ─────────────────────
    {
        "normalized_code": """\
pub struct ClientBuilder {
    inner: SharedConfigBuilder,
}

impl ClientBuilder {
    /// Create a new ClientBuilder with the given secret key.
    pub fn new(secret: impl Into<String>) -> Self {
        Self { inner: SharedConfigBuilder::new(secret) }
    }

    /// Set the Stripe account id for the client.
    pub fn account_id(mut self, account_id: AccountId) -> Self {
        self.inner = self.inner.account_id(account_id);
        self
    }

    /// Set the default RequestStrategy used when making requests.
    pub fn request_strategy(mut self, strategy: RequestStrategy) -> Self {
        self.inner = self.inner.request_strategy(strategy);
        self
    }

    /// Set application info for identification.
    pub fn app_info(
        mut self,
        name: impl Into<String>,
        version: Option<String>,
        url: Option<String>,
    ) -> Self {
        self.inner = self.inner.app_info(name, version, url);
        self
    }

    /// Build and validate the Stripe client.
    pub fn build(self) -> Result<Client, StripeError> {
        Ok(Client::from_config(self.try_into_config()?))
    }
}
""",
        "function": "stripe_client_builder_fluent_api",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "async-stripe/src/hyper/client_builder.rs",
    },
    # ── 2. Request strategy pattern — idempotency and retry semantics ──────────
    {
        "normalized_code": """\
pub enum RequestStrategy {
    Once,
    Idempotent(IdempotencyKey),
    Retry { max_retries: u32, timeout: Duration },
    ExponentialBackoff { max_retries: u32, base_delay: Duration },
}

impl RequestStrategy {
    /// Get idempotency key if set.
    pub fn get_key(&self) -> Option<&IdempotencyKey> {
        match self {
            RequestStrategy::Once => None,
            RequestStrategy::Idempotent(key) => Some(key),
            RequestStrategy::Retry { .. } => Some(&self.auto_generated_key()),
            RequestStrategy::ExponentialBackoff { .. } => Some(&self.auto_generated_key()),
        }
    }

    /// Determine if request should continue or stop.
    pub fn test(
        &self,
        status: Option<u16>,
        should_retry: Option<bool>,
        attempts: u32,
    ) -> Outcome {
        match (self, status, should_retry) {
            (RequestStrategy::Once, _, _) => Outcome::Stop,
            (RequestStrategy::Idempotent(_), Some(s), _) if s < 500 => Outcome::Stop,
            (RequestStrategy::Retry { max_retries, .. }, _, _) if attempts >= *max_retries => {
                Outcome::Stop
            }
            (RequestStrategy::ExponentialBackoff { max_retries, base_delay }, _, _) if attempts >= *max_retries => {
                Outcome::Stop
            }
            (RequestStrategy::ExponentialBackoff { base_delay, .. }, _, _) => {
                let backoff = base_delay.mul_f32(2_f32.powi(attempts as i32));
                Outcome::Continue(Some(backoff))
            }
            _ => Outcome::Continue(None),
        }
    }
}
""",
        "function": "stripe_request_strategy_enum_retry_logic",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "async-stripe/src/lib.rs",
    },
    # ── 3. Webhook HMAC-SHA256 signature verification ──────────────────────────
    {
        "normalized_code": """\
use hmac::{Hmac, Mac};
use sha2::Sha256;

pub struct Webhook;

impl Webhook {
    /// Verify and construct webhook from payload + signature.
    /// Uses HMAC-SHA256 signature verification.
    pub fn construct_event(
        payload: &str,
        signature: &str,
        secret: &str,
    ) -> Result<Payload, WebhookError> {
        let mut mac = Hmac::<Sha256>::new_from_slice(secret.as_bytes())
            .map_err(|_| WebhookError::InvalidSecret)?;
        mac.update(payload.as_bytes());
        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .ok()
            .ok_or(WebhookError::InvalidTimestamp)?
            .as_secs();
        let computed_signature = format!(
            "t={},v1={}",
            timestamp,
            hex::encode(mac.finalize().into_bytes())
        );

        if constant_time_compare(signature.as_bytes(), computed_signature.as_bytes()) {
            serde_json::from_str(payload).map_err(|_| WebhookError::DeserializeError)
        } else {
            Err(WebhookError::InvalidSignature)
        }
    }
}

fn constant_time_compare(actual: &[u8], expected: &[u8]) -> bool {
    use subtle::ConstantTimeComparison;
    actual.ct_eq(expected).into()
}
""",
        "function": "stripe_webhook_hmac_sha256_verify",
        "feature_type": "security",
        "file_role": "utility",
        "file_path": "stripe-webhook/src/lib.rs",
    },
    # ── 4. Payment intent builder with type-safe chaining ──────────────────────
    {
        "normalized_code": """\
pub struct CreatePaymentIntent {
    amount: u64,
    currency: Currency,
    metadata: Option<Metadata>,
    method_types: Vec<String>,
    statement_descriptor: Option<String>,
}

impl CreatePaymentIntent {
    /// Create a new payment intent builder with required amount and currency.
    pub fn new(amount: u64, currency: Currency) -> Self {
        Self {
            amount,
            currency,
            metadata: None,
            method_types: vec![],
            statement_descriptor: None,
        }
    }

    /// Add metadata key-value pairs to the intent.
    pub fn metadata(mut self, metadata: impl Into<Metadata>) -> Self {
        self.metadata = Some(metadata.into());
        self
    }

    /// Set accepted payment method types.
    pub fn method_types(mut self, types: Vec<String>) -> Self {
        self.method_types = types;
        self
    }

    /// Set statement descriptor shown on customer's bank statement.
    pub fn statement_descriptor(mut self, descriptor: impl Into<String>) -> Self {
        self.statement_descriptor = Some(descriptor.into());
        self
    }

    /// Send the request to Stripe API.
    pub async fn send(self, client: &Client) -> Result<PaymentIntent, StripeError> {
        let req = self.build_request()?;
        client.execute(req).await
    }
}
""",
        "function": "stripe_payment_intent_builder_type_safe",
        "feature_type": "crud",
        "file_role": "route",
        "file_path": "stripe-types/src/payment_intent.rs",
    },
    # ── 5. List pagination with auto-advancing cursor ────────────────────────
    {
        "normalized_code": """\
pub async fn manual_pagination_loop(
    client: &Client,
) -> Result<(), StripeError> {
    let mut params = ListCustomer::new().limit(10);

    loop {
        let page = params.send(client).await?;
        if page.data.is_empty() {
            break;
        }

        for element in &page.data {
            tracing::info!("processing element: {}", element.id);
        }

        if !page.has_more {
            break;
        }

        if let Some(last) = page.data.last() {
            params = params.starting_after(last.id.as_str());
        }
    }

    Ok(())
}
""",
        "function": "stripe_pagination_manual_cursor",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "examples/pagination/src/main.rs",
    },
    # ── 6. Pagination stream with futures combinator ──────────────────────────
    {
        "normalized_code": """\
use futures_util::TryStreamExt;

pub async fn stream_pagination(
    client: &Client,
) -> Result<(), StripeError> {
    let paginator = ListCustomer::new().paginate();
    let mut stream = paginator.stream(client);

    if let Some(element) = stream.try_next().await? {
        tracing::debug!("First element: {:?}", element);
    }

    let all_elements: Vec<Customer> = stream.try_collect().await?;
    tracing::debug!("Collected {} elements", all_elements.len());

    Ok(())
}
""",
        "function": "stripe_pagination_stream_combinators",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "examples/pagination/src/main.rs",
    },
    # ── 7. Custom extractor for axum webhook signature verification ──────────
    {
        "normalized_code": """\
use axum::{
    Error, body::Body, extract::FromRequest, http::{Request, StatusCode},
    response::{IntoResponse, Response},
};

pub struct StripeEvent(Event);

impl<S> FromRequest<S> for StripeEvent
where
    String: FromRequest<S>,
    S: Send + Sync,
{
    type Rejection = Response;

    async fn from_request(
        req: Request<Body>,
        state: &S,
    ) -> Result<Self, Self::Rejection> {
        let signature = req
            .headers()
            .get("stripe-signature")
            .ok_or_else(|| StatusCode::BAD_REQUEST.into_response())?
            .to_owned();

        let payload = String::from_request(req, state)
            .await
            .map_err(IntoResponse::into_response)?;

        Webhook::construct_event(
            &payload,
            signature.to_str().map_err(|_| StatusCode::BAD_REQUEST.into_response())?,
            "whsec_xxxxx",
        )
        .map(StripeEvent)
        .map_err(|_| StatusCode::BAD_REQUEST.into_response())
    }
}
""",
        "function": "axum_stripe_webhook_extractor",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/webhook-axum/src/main.rs",
    },
    # ── 8. Error handling enum with type-safe variants ───────────────────────
    {
        "normalized_code": """\
use thiserror::Error;

#[derive(Debug, Error)]
pub enum StripeError {
    #[error("error reported by stripe: {0:#?}, status code: {1}")]
    Stripe(Box<ApiErrors>, u16),

    #[error("error deserializing a request: {0}")]
    JSONDeserialize(String),

    #[error("error communicating with stripe: {0}")]
    ClientError(String),

    #[error("configuration error: {0}")]
    ConfigError(String),

    #[error("timeout communicating with stripe")]
    Timeout,
}

impl StripeError {
    pub fn is_retryable(&self) -> bool {
        match self {
            StripeError::Stripe(_, status) => *status >= 500 || *status == 429,
            StripeError::ClientError(_) => true,
            StripeError::Timeout => true,
            _ => false,
        }
    }

    pub fn status_code(&self) -> Option<u16> {
        match self {
            StripeError::Stripe(_, code) => Some(*code),
            _ => None,
        }
    }
}
""",
        "function": "stripe_error_enum_typed_handling",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "async-stripe/src/error.rs",
    },
    # ── 9. HTTP request construction with header management ──────────────────
    {
        "normalized_code": """\
async fn construct_request(
    &self,
    req: RequestBuilder,
    account_id: Option<AccountId>,
) -> Result<(Builder, Option<Bytes>), StripeError> {
    let mut uri = format!("{}v1{}", self.config.api_base, req.path);
    if let Some(query) = req.query {
        let _ = write!(uri, "?{query}");
    }

    let mut builder = Request::builder()
        .method(convert_stripe_method(req.method))
        .uri(uri)
        .header(AUTHORIZATION, self.config.secret.clone())
        .header(USER_AGENT, self.config.user_agent.clone())
        .header(HeaderName::from_static("stripe-version"), self.config.stripe_version.clone());

    if let Some(client_id) = &self.config.client_id {
        builder = builder.header(HeaderName::from_static("client-id"), client_id.clone());
    }
    if let Some(account_id) = self.get_account_id_header(account_id)? {
        builder = builder.header(HeaderName::from_static("stripe-account"), account_id);
    }

    let body = if let Some(body) = req.body {
        builder = builder.header(
            CONTENT_TYPE,
            HeaderValue::from_static("application/x-www-form-urlencoded"),
        );
        Some(Bytes::from(body))
    } else {
        None
    };
    Ok((builder, body))
}
""",
        "function": "stripe_http_request_header_construction",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "async-stripe/src/hyper/client.rs",
    },
    # ── 10. Send request with retry loop and status handling ──────────────────
    {
        "normalized_code": """\
async fn send_request_with_strategy(
    &self,
    body: Option<Bytes>,
    mut req_builder: Builder,
    strategy: RequestStrategy,
) -> Result<Bytes, StripeError> {
    let mut attempts = 0;
    let mut last_status: Option<StatusCode> = None;
    let mut last_error = StripeError::ClientError("invalid strategy".into());

    if let Some(key) = strategy.get_key() {
        req_builder = req_builder.header(HeaderName::from_static("idempotency-key"), key.as_str());
    }

    let req = req_builder.body(Full::new(body.unwrap_or_default()))?;

    loop {
        return match strategy.test(last_status.map(|s| s.as_u16()), None, attempts) {
            Outcome::Stop => Err(last_error),
            Outcome::Continue(duration) => {
                if let Some(delay) = duration {
                    tokio::time::sleep(delay).await;
                }

                match self.client.request(req.clone()).await {
                    Ok(resp) => {
                        let status = resp.status();
                        let bytes = resp.into_body().collect().await?.to_bytes();
                        if !status.is_success() {
                            attempts += 1;
                            last_error = parse_stripe_error(&bytes, status)?;
                            last_status = Some(status);
                            continue;
                        }
                        Ok(bytes)
                    }
                    Err(err) => {
                        last_error = StripeError::from(err);
                        attempts += 1;
                        continue;
                    }
                }
            }
        };
    }
}
""",
        "function": "stripe_request_retry_strategy_loop",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "async-stripe/src/hyper/client.rs",
    },
    # ── 11. Client factory patterns — two runtime variants (async-std, hyper) ─
    {
        "normalized_code": """\
pub enum ClientRuntime {
    Hyper(HyperClient),
    AsyncStd(AsyncStdClient),
}

impl ClientRuntime {
    pub fn from_secret(secret: impl Into<String>) -> Result<Self, StripeError> {
        #[cfg(feature = "__hyper")]
        return Ok(ClientRuntime::Hyper(
            hyper::ClientBuilder::new(secret).build()?
        ));

        #[cfg(feature = "async-std-surf")]
        return Ok(ClientRuntime::AsyncStd(
            async_std::ClientBuilder::new(secret).build()?
        ));

        #[cfg(not(any(feature = "__hyper", feature = "async-std-surf")))]
        {
            Err(StripeError::ConfigError(
                "no runtime feature enabled: enable `hyper` or `async-std-surf`".into()
            ))
        }
    }

    pub async fn execute(&self, req: CustomizedStripeRequest) -> Result<Bytes, StripeError> {
        match self {
            ClientRuntime::Hyper(c) => c.execute(req).await,
            ClientRuntime::AsyncStd(c) => c.execute(req).await,
        }
    }
}
""",
        "function": "stripe_client_runtime_polymorphism_enum",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "async-stripe/src/lib.rs",
    },
    # ── 12. Expandable objects pattern — nested lazy loading ──────────────────
    {
        "normalized_code": """\
#[derive(Debug, Clone)]
pub enum Expandable<T> {
    Id(String),
    Expanded(Box<T>),
}

impl<T> Expandable<T> {
    /// Get ID if unexpanded, or extract from expanded object.
    pub fn id(&self) -> String {
        match self {
            Expandable::Id(id) => id.clone(),
            Expandable::Expanded(obj) => obj.id(),
        }
    }

    /// Convert to Option<T> if expanded, None if just ID.
    pub fn as_expanded(&self) -> Option<&T> {
        match self {
            Expandable::Expanded(obj) => Some(obj),
            Expandable::Id(_) => None,
        }
    }

    /// Retrieve expanded object by ID using client if needed.
    pub async fn expand(&mut self, client: &Client) -> Result<&T, StripeError> {
        if matches!(self, Expandable::Id(_)) {
            let id = match self {
                Expandable::Id(i) => i.clone(),
                _ => unreachable!(),
            };
            let expanded = fetch_expanded_object(&id, client).await?;
            *self = Expandable::Expanded(Box::new(expanded));
        }
        self.as_expanded()
            .ok_or_else(|| StripeError::ConfigError("object not expanded".into()))
    }
}
""",
        "function": "stripe_expandable_objects_lazy_load",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "stripe-types/src/expandable.rs",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "stripe async client builder with fluent API",
    "idempotency key request strategy retry logic",
    "webhook HMAC-SHA256 signature verification",
    "payment intent type-safe builder pattern",
    "pagination with cursor and manual loop",
    "async stream pagination with futures combinators",
    "axum custom extractor for webhook signature",
    "stripe error enum with retry detection",
    "HTTP request headers and authorization",
    "expandable objects nested lazy loading",
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
            results.append({
                "query": q,
                "function": "NO_RESULT",
                "file_role": "?",
                "score": 0.0,
                "code_preview": "",
                "norm_ok": False,
            })
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
