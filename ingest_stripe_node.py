"""
ingest_stripe_node.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
du SDK Stripe Node.js (TypeScript) dans la KB Qdrant V6.

Focus : CORE payment patterns (Stripe client initialization, payment intent creation,
checkout session, subscription management, webhook signature verification, webhook event
routing, customer creation/update, price/product API, idempotency handling, auto-pagination,
error handling/retry, billing portal).

Usage:
    .venv/bin/python3 ingest_stripe_node.py
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
REPO_URL = "https://github.com/stripe/stripe-node.git"
REPO_NAME = "stripe/stripe-node"
REPO_LOCAL = "/tmp/stripe-node"
LANGUAGE = "typescript"
FRAMEWORK = "express"
STACK = "express+stripe+webhooks"
CHARTE_VERSION = "1.0"
TAG = "stripe/stripe-node"
SOURCE_REPO = "https://github.com/stripe/stripe-node"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Stripe = payment processing SDK. Patterns CORE : client initialization,
# payment flows, webhook verification, subscription management, error handling.
# U-5 mapping: customer→xxx, customers→xxxs, payment→payment (generic), intent→sequence,
# session→context, subscription→membership, invoice→statement, event→webhook_event,
# charge→debit, price→cost, product→offering, checkout→commerce.

PATTERNS: list[dict] = [
    # ── 1. Stripe client initialization with API key and config ────────────────
    {
        "normalized_code": """\
import Stripe from 'stripe';

const stripeClient = new Stripe(process.env.STRIPE_API_KEY!, {
  apiVersion: '2024-04-10',
  typescript: true,
  maxNetworkRetries: 3,
  timeout: 30000,
  host: 'api.stripe.com',
  port: 443,
  protocol: 'https:',
});

export async function getStripeClient(): Promise<Stripe> {
  return stripeClient;
}
""",
        "function": "stripe_client_initialization",
        "feature_type": "config",
        "file_role": "dependency",
        "file_path": "src/lib/stripe.ts",
    },
    # ── 2. Create payment intent with idempotency key ──────────────────────────
    {
        "normalized_code": """\
import Stripe from 'stripe';
import crypto from 'crypto';

interface PaymentIntentRequest {
  amount: number;
  currency: string;
  description?: string;
  metadata?: Record<string, string>;
}

async function createPaymentSequence(
  stripeClient: Stripe,
  request: PaymentIntentRequest,
  idempotencyKey?: string
): Promise<Stripe.PaymentIntent> {
  const key = idempotencyKey || crypto.randomUUID();

  const sequence = await stripeClient.paymentIntents.create(
    {
      amount: request.amount,
      currency: request.currency,
      description: request.description,
      metadata: request.metadata,
    },
    {
      idempotencyKey: key,
      timeout: 30000,
    }
  );

  return sequence;
}
""",
        "function": "payment_intent_idempotent_creation",
        "feature_type": "crud",
        "file_role": "route",
        "file_path": "src/handlers/payments.ts",
    },
    # ── 3. Confirm payment intent with payment method ──────────────────────────
    {
        "normalized_code": """\
import Stripe from 'stripe';

async function confirmPaymentSequence(
  stripeClient: Stripe,
  sequenceId: string,
  paymentMethodId: string,
  returnUrl: string
): Promise<Stripe.PaymentIntent> {
  const confirmed = await stripeClient.paymentIntents.confirm(sequenceId, {
    payment_method: paymentMethodId,
    return_url: returnUrl,
  });

  if (
    confirmed.status === 'requires_action' &&
    confirmed.client_secret
  ) {
    return {
      ...confirmed,
      requiresClientAction: true,
    };
  }

  return confirmed;
}
""",
        "function": "payment_intent_confirmation",
        "feature_type": "crud",
        "file_role": "route",
        "file_path": "src/handlers/payments.ts",
    },
    # ── 4. Create checkout session (E-commerce) ───────────────────────────────
    {
        "normalized_code": """\
import Stripe from 'stripe';

interface CommerceSessionRequest {
  offering_ids: string[];
  xxx_id?: string;
  mode: 'payment' | 'subscription' | 'setup';
  successUrl: string;
  cancelUrl: string;
}

async function createCommerceContext(
  stripeClient: Stripe,
  request: CommerceSessionRequest
): Promise<Stripe.Checkout.Session> {
  const lineElements: Stripe.Checkout.SessionCreateParams.LineItem[] =
    request.offering_ids.map((offering_id) => ({
      price: offering_id,
      quantity: 1,
    }));

  const context = await stripeClient.checkout.sessions.create({
    mode: request.mode,
    line_items: lineElements,
    customer: request.xxx_id,
    success_url: request.successUrl,
    cancel_url: request.cancelUrl,
    payment_method_types: ['card'],
  });

  return context;
}
""",
        "function": "checkout_session_creation",
        "feature_type": "crud",
        "file_role": "route",
        "file_path": "src/handlers/checkout.ts",
    },
    # ── 5. Retrieve checkout session with expansions ──────────────────────────
    {
        "normalized_code": """\
import Stripe from 'stripe';

async function getCommerceContext(
  stripeClient: Stripe,
  sessionId: string,
  expand?: string[]
): Promise<Stripe.Checkout.Session> {
  const context = await stripeClient.checkout.sessions.retrieve(sessionId, {
    expand: expand || ['payment_intent', 'subscription', 'customer'],
  });

  return context;
}

async function getCommerceContextLineElements(
  stripeClient: Stripe,
  sessionId: string,
  limit: number = 100
): Promise<Stripe.LineItem[]> {
  const lineElements = await stripeClient.checkout.sessions.listLineItems(
    sessionId,
    { limit }
  );

  return lineElements.data;
}
""",
        "function": "checkout_session_retrieval_expansion",
        "feature_type": "crud",
        "file_role": "route",
        "file_path": "src/handlers/checkout.ts",
    },
    # ── 6. Create or update customer ──────────────────────────────────────────
    {
        "normalized_code": """\
import Stripe from 'stripe';

interface XxxRequest {
  email: string;
  name?: string;
  address?: Stripe.AddressParam;
  metadata?: Record<string, string>;
}

async function createOrUpdateXxx(
  stripeClient: Stripe,
  request: XxxRequest,
  xxxId?: string
): Promise<Stripe.Customer> {
  if (xxxId) {
    const updated = await stripeClient.customers.update(xxxId, {
      email: request.email,
      name: request.name,
      address: request.address,
      metadata: request.metadata,
    });
    return updated;
  }

  const created = await stripeClient.customers.create({
    email: request.email,
    name: request.name,
    address: request.address,
    metadata: request.metadata,
  });

  return created;
}
""",
        "function": "customer_crud_operations",
        "feature_type": "crud",
        "file_role": "route",
        "file_path": "src/handlers/customers.ts",
    },
    # ── 7. Create subscription for customer ───────────────────────────────────
    {
        "normalized_code": """\
import Stripe from 'stripe';

interface MembershipRequest {
  xxx_id: string;
  price_id: string;
  metadata?: Record<string, string>;
  trialDays?: number;
}

async function createMembership(
  stripeClient: Stripe,
  request: MembershipRequest
): Promise<Stripe.Subscription> {
  const membership = await stripeClient.subscriptions.create({
    customer: request.xxx_id,
    line_elements: [
      {
        price: request.price_id,
      },
    ],
    metadata: request.metadata,
    trial_period_days: request.trialDays,
    payment_behavior: 'error_if_incomplete',
    expand: ['latest_invoice.payment_intent'],
  });

  return membership;
}
""",
        "function": "subscription_creation",
        "feature_type": "crud",
        "file_role": "route",
        "file_path": "src/handlers/subscriptions.ts",
    },
    # ── 8. Webhook signature verification ────────────────────────────────────
    {
        "normalized_code": """\
import Stripe from 'stripe';
import { Request } from 'express';

async function verifyWebhookSignature(
  req: Request,
  whSecret: string,
  stripeClient: Stripe
): Promise<Stripe.WebhookEvent> {
  const signature = req.headers['stripe-signature'] as string;

  if (!signature) {
    throw new Error('Missing stripe-signature header');
  }

  const body = (req as any).rawBody as string | Buffer;

  try {
    const webhook_dispatch = Stripe.webhooks.constructEventAsync(
      body,
      signature,
      whSecret
    );
    return webhook_dispatch;
  } catch (err) {
    throw new Error(`Webhook verification failed: ${(err as Error).message}`);
  }
}
""",
        "function": "webhook_signature_verification",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/handlers/webhooks.ts",
    },
    # ── 9. Webhook event router dispatcher ───────────────────────────────────
    {
        "normalized_code": """\
import Stripe from 'stripe';

type WebhookDispatchHandler = (
  webhook_dispatch: Stripe.WebhookEvent
) => Promise<void>;

interface WebhookHandlers {
  'payment_intent.succeeded'?: WebhookDispatchHandler;
  'payment_intent.payment_failed'?: WebhookDispatchHandler;
  'customer.subscription.updated'?: WebhookDispatchHandler;
  'charge.refunded'?: WebhookDispatchHandler;
  'invoice.payment_succeeded'?: WebhookDispatchHandler;
}

async function routeWebhookDispatch(
  webhook_dispatch: Stripe.WebhookEvent,
  handlers: WebhookHandlers
): Promise<void> {
  const handler = handlers[webhook_dispatch.type as keyof WebhookHandlers];

  if (!handler) {
    return;
  }

  try {
    await handler(webhook_dispatch);
  } catch (err) {
    throw new Error(
      `Failed to handle webhook_dispatch ${webhook_dispatch.type}: ${(err as Error).message}`
    );
  }
}
""",
        "function": "webhook_event_routing_dispatcher",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/handlers/webhooks.ts",
    },
    # ── 10. List and paginate customers with auto-pagination ──────────────────
    {
        "normalized_code": """\
import Stripe from 'stripe';

interface PaginationOptions {
  limit?: number;
  startingAfter?: string;
}

async function listXxxsAutoPaginate(
  stripeClient: Stripe,
  opts?: PaginationOptions
): Promise<Stripe.Customer[]> {
  const xxxs: Stripe.Customer[] = [];

  let hasMore = true;
  let startingAfter: string | undefined = opts?.startingAfter;
  const limit = opts?.limit || 100;

  while (hasMore) {
    const page = await stripeClient.customers.list({
      limit: Math.min(limit, 100),
      starting_after: startingAfter,
    });

    xxxs.push(...page.data);
    hasMore = page.has_more;
    if (page.data.length > 0) {
      startingAfter = page.data[page.data.length - 1].id;
    }
  }

  return xxxs;
}
""",
        "function": "customer_auto_pagination",
        "feature_type": "crud",
        "file_role": "route",
        "file_path": "src/handlers/customers.ts",
    },
    # ── 11. Error handling with retry logic ──────────────────────────────────
    {
        "normalized_code": """\
import Stripe from 'stripe';

const RETRYABLE_ERROR_CODES = [
  'api_connection_error',
  'api_error',
  'timeout_error',
  'rate_limit_error',
];

async function executeWithRetry<T>(
  operation: () => Promise<T>,
  maxRetries: number = 3,
  backoffMs: number = 1000
): Promise<T> {
  let lastError: Error | undefined;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await operation();
    } catch (err) {
      lastError = err as Error;
      const stripeErr = err as Stripe.StripeAPIError;

      if (
        !RETRYABLE_ERROR_CODES.includes(stripeErr.code || '') ||
        attempt === maxRetries
      ) {
        throw err;
      }

      const delay = backoffMs * Math.pow(2, attempt);
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }

  throw lastError;
}
""",
        "function": "error_retry_handler",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "src/utils/retry.ts",
    },
    # ── 12. Create and retrieve invoice (billing document) ────────────────────
    {
        "normalized_code": """\
import Stripe from 'stripe';

async function createStatementForXxx(
  stripeClient: Stripe,
  xxxId: string,
  metadata?: Record<string, string>
): Promise<Stripe.Invoice> {
  const statement = await stripeClient.invoices.create({
    customer: xxxId,
    metadata: metadata,
    auto_advance: false,
  });

  return statement;
}

async function retrieveStatementItems(
  stripeClient: Stripe,
  statementId: string,
  limit: number = 100
): Promise<Stripe.LineItem[]> {
  const elements = await stripeClient.invoices.listLineItems(statementId, {
    limit,
  });

  return elements.data;
}
""",
        "function": "invoice_creation_retrieval",
        "feature_type": "crud",
        "file_role": "route",
        "file_path": "src/handlers/invoices.ts",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "Stripe client initialization API key configuration",
    "create payment intent with idempotency key",
    "confirm payment intent with payment method",
    "create checkout session for e-commerce",
    "retrieve checkout session with expansions",
    "customer create or update CRUD",
    "subscription creation recurring billing",
    "webhook signature verification HMAC",
    "webhook event router dispatcher",
    "auto-pagination list customers",
    "error handling retry logic exponential backoff",
    "invoice creation and line items",
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
