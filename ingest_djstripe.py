"""
ingest_djstripe.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de dj-stripe/dj-stripe dans la KB Qdrant V6.

Focus : CORE payment patterns (Stripe integration for Django).
Webhook signature verification, event processing, Stripe object sync (Customer/Subscription),
payment intent handling, subscription lifecycle, idempotency keys, refund processing.

Usage:
    .venv/bin/python3 ingest_djstripe.py
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
REPO_URL = "https://github.com/dj-stripe/dj-stripe.git"
REPO_NAME = "dj-stripe/dj-stripe"
REPO_LOCAL = "/tmp/dj-stripe"
LANGUAGE = "python"
FRAMEWORK = "django"
STACK = "django+stripe+webhooks"
CHARTE_VERSION = "1.0"
TAG = "dj-stripe/dj-stripe"
SOURCE_REPO = "https://github.com/dj-stripe/dj-stripe"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# dj-stripe = Django ORM wrapper for Stripe API.
# CORE patterns : webhook handling, object sync, idempotency, payment flows.
# U-5 : "customer" is OK (Stripe domain term), "user" → "xxx"/"subscriber"

PATTERNS: list[dict] = [
    # ── 1. Webhook signature verification (HMAC-SHA256) ────────────────────────
    {
        "normalized_code": """\
import logging
from django.http import HttpResponseBadRequest

logger = logging.getLogger(__name__)


def verify_webhook_signature(request, webhook_endpoint) -> bool:
    \"\"\"Verify Stripe webhook signature using HMAC-SHA256.

    Args:
        request: Django request object with stripe-signature header
        webhook_endpoint: WebhookEndpoint model instance with secret

    Returns:
        True if signature is valid, False otherwise
    \"\"\"
    signature_header = request.headers.get("stripe-signature", "")
    if not signature_header:
        logger.error("Missing stripe-signature header")
        return False

    try:
        timestamp, signatures = parse_signature_header(signature_header)
    except ValueError:
        logger.error("Invalid signature header format")
        return False

    payload = request.body
    signed_content = f"{timestamp}.{payload.decode() if isinstance(payload, bytes) else payload}"

    expected_sig = compute_hmac(
        webhook_endpoint.secret.encode(),
        signed_content.encode(),
    )

    return any(sig == expected_sig for sig in signatures)
""",
        "function": "webhook_verify_signature_hmac",
        "feature_type": "security",
        "file_role": "utility",
        "file_path": "djstripe/models/webhooks.py",
    },
    # ── 2. Webhook trigger creation and validation ────────────────────────────
    {
        "normalized_code": """\
import json
import logging
from django.db import models

logger = logging.getLogger(__name__)


class WebhookTrigger(models.Model):
    \"\"\"Model to track incoming webhook triggers before processing.\"\"\"

    stripe_webhook_id = models.CharField(max_length=256, unique=True)
    webhook_endpoint = models.ForeignKey(
        "WebhookEndpoint", on_delete=models.CASCADE, related_name="triggers"
    )
    remote_ip = models.GenericIPAddressField()
    payload = models.JSONField()
    valid = models.BooleanField(default=False)
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def from_request(cls, request, webhook_endpoint):
        \"\"\"Create trigger from Django request.

        Verifies signature and parses JSON payload.
        \"\"\"
        payload_json = json.loads(request.body)
        stripe_webhook_id = payload_json.get("id")

        trigger = cls.objects.create(
            stripe_webhook_id=stripe_webhook_id,
            webhook_endpoint=webhook_endpoint,
            remote_ip=get_client_ip(request),
            payload=payload_json,
        )

        # Verify webhook signature
        trigger.valid = verify_webhook_signature(request, webhook_endpoint)
        trigger.save()

        return trigger

    def process(self):
        \"\"\"Process the webhook trigger by dispatching signal.\"\"\"
        if not self.valid or self.processed:
            return False

        webhook_type = self.payload.get("type")
        signal = WEBHOOK_SIGNALS.get(webhook_type)

        if signal:
            signal.send(sender=Webhook, webhook_data=self.payload)
            self.processed = True
            self.save()
            return True
        return False
""",
        "function": "webhook_trigger_creation_validation",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "djstripe/models/webhooks.py",
    },
    # ── 3. Customer sync from Stripe API ───────────────────────────────────────
    {
        "normalized_code": """\
import logging
from django.db import models, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class Customer(models.Model):
    \"\"\"Synced Stripe customer object.\"\"\"

    stripe_id = models.CharField(max_length=255, unique=True, db_index=True)
    stripe_data = models.JSONField()
    account = models.OneToOneField(
        "auth.Account",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stripe_customer",
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delinquent = models.BooleanField(default=False)
    synced_at = models.DateTimeField(auto_now=True)

    @classmethod
    @transaction.atomic
    def sync_from_stripe_data(cls, stripe_customer_data: dict) -> "Customer":
        \"\"\"Create or update customer from Stripe API response.

        Atomically updates customer fields and syncs related objects
        (subscriptions, invoices, charges, payment methods).
        \"\"\"
        stripe_id = stripe_customer_data["id"]
        customer, created = cls.objects.get_or_create(stripe_id=stripe_id)

        customer.stripe_data = stripe_customer_data
        customer.balance = stripe_customer_data.get("balance", 0) / 100
        customer.delinquent = stripe_customer_data.get("delinquent", False)
        customer.save()

        # Sync nested collections
        customer._sync_subscriptions()
        customer._sync_invoices()
        customer._sync_charges()
        customer._sync_payment_methods()

        return customer

    def _sync_subscriptions(self):
        \"\"\"Fetch and sync all subscriptions for this customer.\"\"\"
        subscriptions = stripe.Subscription.list(customer=self.stripe_id)
        for sub_data in subscriptions:
            Subscription.sync_from_stripe_data(sub_data)

    def _sync_invoices(self):
        \"\"\"Fetch and sync all invoices for this customer.\"\"\"
        invoices = stripe.Invoice.list(customer=self.stripe_id)
        for inv_data in invoices:
            Invoice.sync_from_stripe_data(inv_data)

    def _sync_charges(self):
        \"\"\"Fetch and sync all charges for this customer.\"\"\"
        charges = stripe.Charge.list(customer=self.stripe_id)
        for charge_data in charges:
            Charge.sync_from_stripe_data(charge_data)

    def _sync_payment_methods(self):
        \"\"\"Fetch and sync all payment methods for this customer.\"\"\"
        methods = stripe.PaymentMethod.list(
            customer=self.stripe_id, type="card"
        )
        for pm_data in methods:
            PaymentMethod.sync_from_stripe_data(pm_data)
""",
        "function": "customer_sync_nested_objects",
        "feature_type": "sync",
        "file_role": "model",
        "file_path": "djstripe/models/core.py",
    },
    # ── 4. Subscription lifecycle: create, update, cancel ──────────────────────
    {
        "normalized_code": """\
import logging
from datetime import datetime
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class Subscription(models.Model):
    \"\"\"Synced Stripe subscription.\"\"\"

    stripe_id = models.CharField(max_length=255, unique=True, db_index=True)
    customer = models.ForeignKey(
        "Customer", on_delete=models.CASCADE, related_name="subscriptions"
    )
    status = models.CharField(
        max_length=50,
        choices=[
            ("active", "Active"),
            ("past_due", "Past Due"),
            ("canceled", "Canceled"),
            ("unpaid", "Unpaid"),
        ],
    )
    stripe_data = models.JSONField()
    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)

    @classmethod
    def create(cls, customer_id: str, price_id: str, **kwargs) -> "Subscription":
        \"\"\"Create subscription via Stripe API.

        Args:
            customer_id: Stripe customer ID
            price_id: Stripe price/plan ID
            **kwargs: billing_cycle_anchor, off_session, trial_days, etc.

        Returns:
            Subscription instance synced from API response
        \"\"\"
        sub_data = stripe.Subscription.create(
            customer=customer_id,
            line_elements=[{"price": price_id}],
            **kwargs,
        )
        return cls.sync_from_stripe_data(sub_data)

    def update_line_elements(self, elements: list[dict]) -> "Subscription":
        \"\"\"Update subscription line elements (prices/quantities).

        Args:
            elements: [{"id": "si_xxx", "quantity": 2}, ...]

        Returns:
            Updated Subscription
        \"\"\"
        sub_data = stripe.Subscription.modify(
            self.stripe_id,
            line_elements=elements,
        )
        return self.sync_from_stripe_data(sub_data)

    def cancel(self, at_period_end: bool = True) -> "Subscription":
        \"\"\"Cancel subscription.

        Args:
            at_period_end: If True, cancel at end of billing period.
                           If False, cancel immediately.

        Returns:
            Updated Subscription with status 'canceled'
        \"\"\"
        sub_data = stripe.Subscription.delete(
            self.stripe_id,
            invoice_now=(not at_period_end),
        )
        self.refresh_from_stripe()
        return self

    @classmethod
    def sync_from_stripe_data(cls, stripe_sub_data: dict) -> "Subscription":
        \"\"\"Create or update subscription from Stripe API response.\"\"\"
        stripe_id = stripe_sub_data["id"]
        customer_id = stripe_sub_data["customer"]

        sub, _ = cls.objects.get_or_create(
            stripe_id=stripe_id,
            defaults={"customer_id": customer_id},
        )

        sub.stripe_data = stripe_sub_data
        sub.status = stripe_sub_data.get("status")
        sub.cancel_at_period_end = stripe_sub_data.get("cancel_at_period_end", False)
        sub.canceled_at = convert_timestamp(stripe_sub_data.get("canceled_at"))
        sub.current_period_end = convert_timestamp(stripe_sub_data.get("current_period_end"))
        sub.save()

        return sub
""",
        "function": "subscription_lifecycle_crud",
        "feature_type": "crud",
        "file_role": "model",
        "file_path": "djstripe/models/billing.py",
    },
    # ── 5. Payment intent creation and confirmation ────────────────────────────
    {
        "normalized_code": """\
import logging
from decimal import Decimal
from django.db import models

logger = logging.getLogger(__name__)


class PaymentIntent(models.Model):
    \"\"\"Stripe PaymentIntent for collecting payments.\"\"\"

    stripe_id = models.CharField(max_length=255, unique=True, db_index=True)
    customer = models.ForeignKey(
        "Customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_intents",
    )
    amount_cents = models.BigIntegerField()
    currency = models.CharField(max_length=3, default="usd")
    status = models.CharField(
        max_length=50,
        choices=[
            ("requires_payment_method", "Requires Payment Method"),
            ("requires_confirmation", "Requires Confirmation"),
            ("requires_action", "Requires Action"),
            ("processing", "Processing"),
            ("requires_capture", "Requires Capture"),
            ("succeeded", "Succeeded"),
            ("canceled", "Canceled"),
        ],
    )
    client_secret = models.CharField(max_length=255, unique=True)
    idempotency_key = models.CharField(max_length=255, unique=True, null=True)
    stripe_data = models.JSONField()

    @classmethod
    def create(
        cls,
        amount_cents: int,
        currency: str = "usd",
        customer_id: str | None = None,
        idempotency_key: str | None = None,
        **kwargs,
    ) -> "PaymentIntent":
        \"\"\"Create PaymentIntent via Stripe API.

        Args:
            amount_cents: Amount in cents (e.g., 2000 = $20.00)
            currency: Currency code (default: usd)
            customer_id: Stripe customer ID (optional)
            idempotency_key: Unique key for idempotency (prevents double-charges)
            **kwargs: statement_descriptor, off_session, setup_future_usage, etc.

        Returns:
            PaymentIntent instance
        \"\"\"
        headers = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        pi_data = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=currency,
            customer=customer_id,
            **kwargs,
            request_options={"headers": headers} if headers else {},
        )

        return cls.sync_from_stripe_data(pi_data, idempotency_key=idempotency_key)

    def confirm(self, payment_method_id: str | None = None) -> "PaymentIntent":
        \"\"\"Confirm PaymentIntent to initiate payment.

        Args:
            payment_method_id: Stripe payment method ID (optional)

        Returns:
            Updated PaymentIntent after confirmation
        \"\"\"
        pi_data = stripe.PaymentIntent.confirm(
            self.stripe_id,
            payment_method=payment_method_id,
        )
        return self.sync_from_stripe_data(pi_data)

    @classmethod
    def sync_from_stripe_data(
        cls, stripe_pi_data: dict, idempotency_key: str | None = None
    ) -> "PaymentIntent":
        \"\"\"Create or update PaymentIntent from Stripe API response.\"\"\"
        stripe_id = stripe_pi_data["id"]
        customer_id = stripe_pi_data.get("customer")

        pi, _ = cls.objects.get_or_create(stripe_id=stripe_id)

        pi.customer_id = customer_id
        pi.amount_cents = stripe_pi_data.get("amount")
        pi.currency = stripe_pi_data.get("currency", "usd")
        pi.status = stripe_pi_data.get("status")
        pi.client_secret = stripe_pi_data.get("client_secret")
        pi.idempotency_key = idempotency_key
        pi.stripe_data = stripe_pi_data
        pi.save()

        return pi
""",
        "function": "payment_intent_create_confirm",
        "feature_type": "crud",
        "file_role": "model",
        "file_path": "djstripe/models/core.py",
    },
    # ── 6. Idempotency key generation and tracking ────────────────────────────
    {
        "normalized_code": """\
import logging
import uuid
from datetime import timedelta
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class IdempotencyKey(models.Model):
    \"\"\"Track idempotency keys for Stripe API requests.

    Prevents duplicate charges if client retries failed requests.
    Keys expire after 24 hours (Stripe standard).
    \"\"\"

    uuid = models.UUIDField(unique=True, db_index=True)
    operation_name = models.CharField(max_length=255, db_index=True)
    result_data = models.JSONField(null=True, blank=True)
    status = models.CharField(
        max_length=50,
        choices=[
            ("pending", "Pending"),
            ("success", "Success"),
            ("failed", "Failed"),
        ],
        default="pending",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["uuid", "operation_name"]),
        ]

    @classmethod
    def generate(cls, operation_name: str) -> "IdempotencyKey":
        \"\"\"Generate a new idempotency key.

        Args:
            operation_name: Name of the operation (e.g., 'create_payment_intent')

        Returns:
            IdempotencyKey instance
        \"\"\"
        key = cls.objects.create(
            uuid=uuid.uuid4(),
            operation_name=operation_name,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        return key

    @classmethod
    def lookup(cls, key_uuid: uuid.UUID) -> "IdempotencyKey" | None:
        \"\"\"Look up idempotency key result (if already processed).

        Returns:
            IdempotencyKey if found and not expired, None otherwise
        \"\"\"
        try:
            key = cls.objects.get(uuid=key_uuid)
            if timezone.now() > key.expires_at:
                key.delete()
                return None
            return key
        except cls.DoesNotExist:
            return None

    @classmethod
    def cleanup_expired(cls) -> int:
        \"\"\"Delete expired idempotency keys.

        Returns:
            Number of deleted keys
        \"\"\"
        count, _ = cls.objects.filter(
            expires_at__lt=timezone.now()
        ).delete()
        return count
""",
        "function": "idempotency_key_generation_tracking",
        "feature_type": "utility",
        "file_role": "model",
        "file_path": "djstripe/models/base.py",
    },
    # ── 7. Refund processing and tracking ──────────────────────────────────────
    {
        "normalized_code": """\
import logging
from decimal import Decimal
from django.db import models

logger = logging.getLogger(__name__)


class Refund(models.Model):
    \"\"\"Stripe refund for a charge.\"\"\"

    stripe_id = models.CharField(max_length=255, unique=True, db_index=True)
    charge = models.ForeignKey(
        "Charge", on_delete=models.CASCADE, related_name="refunds"
    )
    amount_cents = models.BigIntegerField()
    currency = models.CharField(max_length=3)
    status = models.CharField(
        max_length=50,
        choices=[
            ("succeeded", "Succeeded"),
            ("failed", "Failed"),
            ("pending", "Pending"),
            ("canceled", "Canceled"),
        ],
    )
    reason = models.CharField(
        max_length=50,
        choices=[
            ("duplicate", "Duplicate"),
            ("fraudulent", "Fraudulent"),
            ("requested_by_customer", "Requested by Customer"),
        ],
        null=True,
        blank=True,
    )
    stripe_data = models.JSONField()

    @classmethod
    def create(
        cls,
        charge_id: str,
        amount_cents: int | None = None,
        reason: str | None = None,
        metadata: dict | None = None,
    ) -> "Refund":
        \"\"\"Create refund via Stripe API.

        Args:
            charge_id: Stripe charge ID
            amount_cents: Amount to refund in cents. None = full refund.
            reason: Refund reason (duplicate, fraudulent, requested_by_customer)
            metadata: Additional metadata dict

        Returns:
            Refund instance
        \"\"\"
        refund_kwargs = {"charge": charge_id}
        if amount_cents is not None:
            refund_kwargs["amount"] = amount_cents
        if reason:
            refund_kwargs["reason"] = reason
        if metadata:
            refund_kwargs["metadata"] = metadata

        refund_data = stripe.Refund.create(**refund_kwargs)
        return cls.sync_from_stripe_data(refund_data)

    @classmethod
    def sync_from_stripe_data(cls, stripe_refund_data: dict) -> "Refund":
        \"\"\"Create or update refund from Stripe API response.\"\"\"
        stripe_id = stripe_refund_data["id"]
        charge_id = stripe_refund_data["charge"]

        refund, _ = cls.objects.get_or_create(
            stripe_id=stripe_id,
            defaults={"charge_id": charge_id},
        )

        refund.amount_cents = stripe_refund_data.get("amount")
        refund.currency = stripe_refund_data.get("currency")
        refund.status = stripe_refund_data.get("status")
        refund.reason = stripe_refund_data.get("reason")
        refund.stripe_data = stripe_refund_data
        refund.save()

        return refund
""",
        "function": "refund_create_and_sync",
        "feature_type": "crud",
        "file_role": "model",
        "file_path": "djstripe/models/core.py",
    },
    # ── 8. Invoice generation and payment ──────────────────────────────────────
    {
        "normalized_code": """\
import logging
from datetime import datetime
from django.db import models

logger = logging.getLogger(__name__)


class Invoice(models.Model):
    \"\"\"Stripe invoice (billing document).\"\"\"

    stripe_id = models.CharField(max_length=255, unique=True, db_index=True)
    customer = models.ForeignKey(
        "Customer", on_delete=models.CASCADE, related_name="invoices"
    )
    subscription = models.ForeignKey(
        "Subscription",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invoices",
    )
    amount_cents = models.BigIntegerField()
    currency = models.CharField(max_length=3)
    status = models.CharField(
        max_length=50,
        choices=[
            ("draft", "Draft"),
            ("open", "Open"),
            ("paid", "Paid"),
            ("uncollectible", "Uncollectible"),
            ("void", "Void"),
        ],
    )
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    stripe_data = models.JSONField()

    @classmethod
    def sync_from_stripe_data(cls, stripe_invoice_data: dict) -> "Invoice":
        \"\"\"Create or update invoice from Stripe API response.\"\"\"
        stripe_id = stripe_invoice_data["id"]
        customer_id = stripe_invoice_data["customer"]

        inv, _ = cls.objects.get_or_create(
            stripe_id=stripe_id,
            defaults={"customer_id": customer_id},
        )

        inv.amount_cents = stripe_invoice_data.get("total")
        inv.currency = stripe_invoice_data.get("currency")
        inv.status = stripe_invoice_data.get("status")
        inv.period_start = convert_timestamp(stripe_invoice_data.get("period_start"))
        inv.period_end = convert_timestamp(stripe_invoice_data.get("period_end"))
        inv.due_date = convert_timestamp(stripe_invoice_data.get("due_date"))
        inv.paid_at = convert_timestamp(stripe_invoice_data.get("paid_at"))
        inv.stripe_data = stripe_invoice_data

        sub_id = stripe_invoice_data.get("subscription")
        if sub_id:
            inv.subscription_id = sub_id

        inv.save()
        return inv

    def finalize(self) -> "Invoice":
        \"\"\"Finalize draft invoice (moves to 'open' status).\"\"\"
        inv_data = stripe.Invoice.finalize_invoice(self.stripe_id)
        return self.sync_from_stripe_data(inv_data)

    def pay(self) -> "Invoice":
        \"\"\"Pay invoice via Stripe API.\"\"\"
        inv_data = stripe.Invoice.pay(self.stripe_id)
        return self.sync_from_stripe_data(inv_data)
""",
        "function": "invoice_generate_and_pay",
        "feature_type": "crud",
        "file_role": "model",
        "file_path": "djstripe/models/billing.py",
    },
    # ── 9. Payment method storage and attachment ───────────────────────────────
    {
        "normalized_code": """\
import logging
from django.db import models

logger = logging.getLogger(__name__)


class PaymentMethod(models.Model):
    \"\"\"Stripe payment method (card, bank account, etc.).\"\"\"

    stripe_id = models.CharField(max_length=255, unique=True, db_index=True)
    customer = models.ForeignKey(
        "Customer",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="payment_methods",
    )
    type = models.CharField(
        max_length=50,
        choices=[
            ("card", "Card"),
            ("bank_account", "Bank Account"),
            ("wallet", "Wallet"),
        ],
    )
    billing_details = models.JSONField(default=dict)
    card_data = models.JSONField(null=True, blank=True)
    stripe_data = models.JSONField()

    @classmethod
    def attach_to_customer(
        cls, payment_method_id: str, customer_id: str
    ) -> "PaymentMethod":
        \"\"\"Attach payment method to customer.

        Args:
            payment_method_id: Stripe payment method ID
            customer_id: Stripe customer ID

        Returns:
            PaymentMethod instance
        \"\"\"
        pm_data = stripe.PaymentMethod.attach(
            payment_method_id,
            customer=customer_id,
        )
        return cls.sync_from_stripe_data(pm_data)

    def detach(self) -> bool:
        \"\"\"Detach payment method from customer.\"\"\"
        stripe.PaymentMethod.detach(self.stripe_id)
        self.customer = None
        self.save()
        return True

    @classmethod
    def sync_from_stripe_data(cls, stripe_pm_data: dict) -> "PaymentMethod":
        \"\"\"Create or update payment method from Stripe API response.\"\"\"
        stripe_id = stripe_pm_data["id"]
        customer_id = stripe_pm_data.get("customer")

        pm, _ = cls.objects.get_or_create(stripe_id=stripe_id)

        pm.customer_id = customer_id
        pm.type = stripe_pm_data.get("type")
        pm.billing_details = stripe_pm_data.get("billing_details", {})
        pm.card_data = stripe_pm_data.get("card")
        pm.stripe_data = stripe_pm_data
        pm.save()

        return pm
""",
        "function": "payment_method_attach_detach",
        "feature_type": "crud",
        "file_role": "model",
        "file_path": "djstripe/models/payment_methods.py",
    },
    # ── 10. Webhook signal dispatch (handlers registration) ────────────────────
    {
        "normalized_code": """\
import logging
from django.dispatch import Signal

logger = logging.getLogger(__name__)

# Define signal mappings for all webhook trigger types
WEBHOOK_SIGNALS: dict[str, Signal] = {
    "customer.created": Signal(),
    "customer.updated": Signal(),
    "customer.deleted": Signal(),
    "payment_intent.succeeded": Signal(),
    "payment_intent.payment_failed": Signal(),
    "invoice.created": Signal(),
    "invoice.finalized": Signal(),
    "invoice.payment_succeeded": Signal(),
    "invoice.payment_failed": Signal(),
    "charge.refunded": Signal(),
    "charge.dispute.created": Signal(),
    "subscription.created": Signal(),
    "subscription.updated": Signal(),
    "subscription.deleted": Signal(),
}


def register_webhook_handler(webhook_type: str, handler_func):
    \"\"\"Register a handler function for a webhook trigger type.

    Args:
        webhook_type: Stripe webhook type (e.g., 'customer.updated')
        handler_func: Callable(sender, webhook, **kwargs)
    \"\"\"
    signal = WEBHOOK_SIGNALS.get(webhook_type)
    if not signal:
        logger.warning(f"Webhook type '{webhook_type}' not registered")
        return False

    signal.connect(handler_func, weak=False)
    logger.info(f"Registered handler for '{webhook_type}'")
    return True


def dispatch_webhook(webhook_type: str, webhook_data: dict):
    \"\"\"Dispatch webhook trigger to all registered handlers.

    Args:
        webhook_type: Stripe webhook type
        webhook_data: Full webhook data dict from Stripe
    \"\"\"
    signal = WEBHOOK_SIGNALS.get(webhook_type)
    if not signal:
        logger.warning(f"No signal registered for '{webhook_type}'")
        return

    signal.send(sender="webhook", webhook=webhook_data)
    logger.info(f"Dispatched '{webhook_type}' to {signal.receiver_count} handlers")
""",
        "function": "webhook_signal_dispatch_handlers",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "djstripe/signals.py",
    },
    # ── 11. Charge sync with balance transaction ───────────────────────────────
    {
        "normalized_code": """\
import logging
from decimal import Decimal
from django.db import models

logger = logging.getLogger(__name__)


class Charge(models.Model):
    \"\"\"Stripe charge (payment transaction).\"\"\"

    stripe_id = models.CharField(max_length=255, unique=True, db_index=True)
    customer = models.ForeignKey(
        "Customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="charges",
    )
    invoice = models.ForeignKey(
        "Invoice",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="charges",
    )
    payment_intent = models.ForeignKey(
        "PaymentIntent",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="charges",
    )
    balance_transaction = models.ForeignKey(
        "BalanceTransaction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="charges",
    )
    amount_cents = models.BigIntegerField()
    amount_refunded_cents = models.BigIntegerField(default=0)
    currency = models.CharField(max_length=3)
    paid = models.BooleanField(default=False)
    captured = models.BooleanField(default=False)
    disputed = models.BooleanField(default=False)
    stripe_data = models.JSONField()

    @classmethod
    def sync_from_stripe_data(cls, stripe_charge_data: dict) -> "Charge":
        \"\"\"Create or update charge from Stripe API response.\"\"\"
        stripe_id = stripe_charge_data["id"]

        charge, _ = cls.objects.get_or_create(stripe_id=stripe_id)

        charge.amount_cents = stripe_charge_data.get("amount")
        charge.amount_refunded_cents = stripe_charge_data.get("amount_refunded", 0)
        charge.currency = stripe_charge_data.get("currency")
        charge.paid = stripe_charge_data.get("paid", False)
        charge.captured = stripe_charge_data.get("captured", False)
        charge.disputed = stripe_charge_data.get("disputed", False)

        # Foreign keys
        charge.customer_id = stripe_charge_data.get("customer")
        charge.invoice_id = stripe_charge_data.get("invoice")
        charge.payment_intent_id = stripe_charge_data.get("payment_intent")
        balance_transaction_id = stripe_charge_data.get("balance_transaction")
        if balance_transaction_id:
            charge.balance_transaction_id = balance_transaction_id

        charge.stripe_data = stripe_charge_data
        charge.save()

        return charge

    def capture(self, amount_cents: int | None = None) -> "Charge":
        \"\"\"Capture a charge (for uncaptured auth-only charges).\"\"\"
        charge_data = stripe.Charge.capture(
            self.stripe_id,
            amount=amount_cents,
        )
        return self.sync_from_stripe_data(charge_data)
""",
        "function": "charge_sync_with_balance_transaction",
        "feature_type": "sync",
        "file_role": "model",
        "file_path": "djstripe/models/core.py",
    },
    # ── 12. Stripe API object expansion and field selection ────────────────────
    {
        "normalized_code": """\
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def build_stripe_api_request(
    expand_fields: list[str] | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    \"\"\"Build kwargs for Stripe API requests with field expansion.

    Args:
        expand_fields: List of fields to expand (e.g., ['customer', 'balance_transaction'])
        api_key: Stripe API key (defaults to settings.STRIPE_SECRET_KEY)

    Returns:
        kwargs dict for stripe.Xxx.retrieve(..., **kwargs)
    \"\"\"
    kwargs = {}

    if expand_fields:
        kwargs["expand"] = expand_fields

    if api_key:
        kwargs["api_key"] = api_key

    return kwargs


def retrieve_with_expand(
    model_class,
    stripe_id: str,
    expand_fields: list[str] | None = None,
    api_key: str | None = None,
) -> dict:
    \"\"\"Retrieve Stripe object with nested field expansion.

    Prevents N+1 queries by expanding related objects in a single API call.

    Args:
        model_class: Stripe API resource class (stripe.Charge, stripe.Customer, etc.)
        stripe_id: Stripe object ID
        expand_fields: Fields to expand (e.g., ['customer', 'payment_intent.charges'])
        api_key: Stripe API key

    Returns:
        API response dict with expanded nested objects
    \"\"\"
    if expand_fields is None:
        expand_fields = getattr(model_class, "expand_fields", [])

    request_kwargs = build_stripe_api_request(
        expand_fields=expand_fields, api_key=api_key
    )
    api_obj = model_class.retrieve(stripe_id, **request_kwargs)
    return api_obj
""",
        "function": "stripe_api_request_building_expansion",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "djstripe/models/base.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "webhook signature verification HMAC-SHA256 Stripe",
    "create and sync customer from Stripe API",
    "subscription create update cancel lifecycle",
    "payment intent creation and confirmation flow",
    "idempotency key generation prevent duplicate charges",
    "refund processing full and partial refunds",
    "invoice generation finalization and payment",
    "payment method attach and detach to customer",
    "webhook event signal dispatch and handlers",
    "charge sync with balance transaction data",
    "Stripe API field expansion nested objects",
]


def clone_repo() -> None:
    import os

    if os.path.isdir(REPO_LOCAL):
        return
    subprocess.run(
        ["git", "clone", REPO_URL, REPO_LOCAL, "--depth=1"],
        check=True,
        capture_output=True,
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
            results.append(
                {
                    "query": q,
                    "function": hit.payload.get("function", "?"),
                    "file_role": hit.payload.get("file_role", "?"),
                    "score": hit.score,
                    "code_preview": hit.payload.get("normalized_code", "")[:50],
                }
            )
        else:
            results.append(
                {
                    "query": q,
                    "function": "NO_RESULT",
                    "file_role": "?",
                    "score": 0.0,
                    "code_preview": "",
                }
            )
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
