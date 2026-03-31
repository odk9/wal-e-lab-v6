"""
ingest_fastapi_mail.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de sabuhish/fastapi-mail dans la KB Qdrant V6.

Focus : CORE email patterns (SMTP config, message schema, async send, templates,
attachments, bulk dispatch, email validation, connection pooling).

Usage:
    .venv/bin/python3 ingest_fastapi_mail.py
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
REPO_URL = "https://github.com/sabuhish/fastapi-mail.git"
REPO_NAME = "sabuhish/fastapi-mail"
REPO_LOCAL = "/tmp/fastapi-mail"
LANGUAGE = "python"
FRAMEWORK = "fastapi"
STACK = "fastapi+aiosmtplib+jinja2+email"
CHARTE_VERSION = "1.0"
TAG = "sabuhish/fastapi-mail"
SOURCE_REPO = "https://github.com/sabuhish/fastapi-mail"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# FastAPI-Mail = async email sending (SMTP, Jinja2 templates, attachments).
# Patterns CORE : SMTP config, message building, async send, template rendering.
# U-5 : entités remplacées par Xxx (MessageSchema → envelope), xxx (recipient → recipient), etc.

PATTERNS: list[dict] = [
    # ── 1. SMTP connection config (aiosmtplib async context manager) ─────────
    {
        "normalized_code": """\
from typing import Optional
from pydantic_settings import BaseSettings as Settings
from pydantic import DirectoryPath, EmailStr, SecretStr, conint
from aiosmtplib.api import DEFAULT_TIMEOUT
from jinja2 import Environment, FileSystemLoader


class XxxConfig(Settings):
    \"\"\"Configuration for email server connection.\"\"\"

    smtp_xxx: str
    smtp_pwd: SecretStr
    smtp_port: int
    smtp_host: str
    smtp_starttls: bool
    smtp_ssl_tls: bool
    smtp_debug: conint(gt=-1, lt=2) = 0
    sender_addr: EmailStr
    sender_name: Optional[str] = None
    template_dir: Optional[DirectoryPath] = None
    suppress_send: conint(gt=-1, lt=2) = 0
    use_credentials: bool = True
    validate_certs: bool = True
    timeout: int = DEFAULT_TIMEOUT
    local_hostname: Optional[str] = None
    cert_bundle: Optional[str] = None

    def template_engine(self) -> Environment:
        \"\"\"Get Jinja2 template environment.\"\"\"
        folder = self.template_dir
        if not folder:
            raise ValueError("template_dir is required for template rendering")
        return Environment(loader=FileSystemLoader(folder))
""",
        "function": "smtp_config_class_aiosmtplib",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "fastapi_mail/config.py",
    },
    # ── 2. SMTP async connection with context manager ──────────────────────
    {
        "normalized_code": """\
import aiosmtplib
from fastapi_mail.config import XxxConfig


class XxxConnection:
    \"\"\"Async SMTP connection manager.\"\"\"

    def __init__(self, config: XxxConfig) -> None:
        if not isinstance(config, XxxConfig):
            raise ValueError("config must be XxxConfig instance")
        self.config = config

    async def __aenter__(self) -> "XxxConnection":
        \"\"\"Open SMTP connection on context entry.\"\"\"
        await self._setup_connection()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        \"\"\"Close SMTP connection on context exit.\"\"\"
        if not self.config.suppress_send:
            await self.session.quit()

    async def _setup_connection(self) -> None:
        \"\"\"Configure async SMTP session with credentials.\"\"\"
        try:
            self.session = aiosmtplib.SMTP(
                hostname=self.config.smtp_host,
                timeout=self.config.timeout,
                port=self.config.smtp_port,
                use_tls=self.config.smtp_ssl_tls,
                start_tls=self.config.smtp_starttls,
                validate_certs=self.config.validate_certs,
                local_hostname=self.config.local_hostname,
                cert_bundle=self.config.cert_bundle,
            )

            if not self.config.suppress_send:
                await self.session.connect()
                if self.config.use_credentials:
                    await self.session.login(
                        self.config.smtp_xxx,
                        self.config.smtp_pwd.get_secret_value(),
                    )

        except Exception as error:
            raise RuntimeError(f"SMTP connection failed: {error}")
""",
        "function": "smtp_async_context_manager",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "fastapi_mail/connection.py",
    },
    # ── 3. Message schema with Pydantic V2 validation ──────────────────────
    {
        "normalized_code": """\
from enum import Enum
from typing import Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, EmailStr, NameEmail, field_validator
from starlette.datastructures import UploadFile


class MultipartSubtypeEnum(Enum):
    \"\"\"MIME multipart subtypes.\"\"\"
    mixed = "mixed"
    alternative = "alternative"
    related = "related"


class MessageType(Enum):
    \"\"\"Email body content type.\"\"\"
    plain = "plain"
    html = "html"


class XxxSchema(BaseModel):
    \"\"\"Email envelope schema.\"\"\"

    recipients: List[NameEmail]
    attachments: List[Union[UploadFile, Dict, str]] = []
    subject: str = ""
    body: Optional[Union[str, list]] = None
    alternative_body: Optional[str] = None
    template_body: Optional[Union[list, dict, str]] = None
    cc: List[NameEmail] = []
    bcc: List[NameEmail] = []
    reply_to: List[NameEmail] = []
    sender_addr: Optional[EmailStr] = None
    sender_name: Optional[str] = None
    charset: str = "utf-8"
    subtype: MessageType
    multipart_subtype: MultipartSubtypeEnum = MultipartSubtypeEnum.mixed
    headers: Optional[Dict] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator("attachments")
    @classmethod
    def validate_attachments(cls, attachments: list) -> list:
        \"\"\"Validate attachment paths and types.\"\"\"
        validated = []
        for attachment in attachments:
            if isinstance(attachment, str):
                if not isinstance(attachment, (str, bytes)):
                    raise ValueError("attachment path must be string")
            validated.append(attachment)
        return validated
""",
        "function": "email_message_schema_pydantic_v2",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "fastapi_mail/schemas.py",
    },
    # ── 4. Email message MIME building (headers, body, attachments) ────────
    {
        "normalized_code": """\
import time
from email.encoders import encode_base64
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from typing import Any, Union


class MailMsg:
    \"\"\"Build MIME email envelope.\"\"\"

    def __init__(self, envelope: Any) -> None:
        self.recipients = envelope.recipients
        self.attachments = envelope.attachments
        self.subject = envelope.subject
        self.body = envelope.body
        self.alternative_body = envelope.alternative_body
        self.template_body = envelope.template_body
        self.cc = envelope.cc
        self.bcc = envelope.bcc
        self.reply_to = envelope.reply_to
        self.charset = envelope.charset
        self.subtype = envelope.subtype
        self.multipart_subtype = envelope.multipart_subtype
        self.headers = envelope.headers
        msg_id_key = "message-id"
        self.msg_id = self.headers.get(msg_id_key) if self.headers else None
        if not self.msg_id:
            self.msg_id = make_msgid()

    def _mimetext(self, text: str, subtype: str) -> MIMEText:
        \"\"\"Create MIMEText object.\"\"\"
        return MIMEText(text, _subtype=subtype, _charset=self.charset)

    async def attach_file(self, envelope_obj: MIMEMultipart, attachment: Any) -> None:
        \"\"\"Attach file to envelope with base64 encoding.\"\"\"
        for file, file_meta in attachment:
            part = MIMEBase(_maintype="application", _subtype="octet-stream")
            await file.seek(0)
            part.set_payload(await file.read())
            encode_base64(part)
            await file.close()

            if file_meta and "headers" in file_meta:
                for header_name, header_val in file_meta["headers"].items():
                    part.add_header(header_name, header_val)

            if not part.get("Content-Disposition"):
                filename = file.filename
                part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=("UTF8", "", filename),
                )

            envelope_obj.attach(part)

    async def _build_mime(self, sender: str) -> Union[MIMEMultipart, MIMEText]:
        \"\"\"Build complete email envelope with headers and content.\"\"\"
        self.envelope_obj = MIMEMultipart(self.multipart_subtype.value)
        self.envelope_obj.set_charset(self.charset)

        if self.template_body:
            self.envelope_obj.attach(self._mimetext(self.template_body, self.subtype.value))
        elif self.body:
            self.envelope_obj.attach(self._mimetext(self.body, self.subtype.value))

        self.envelope_obj["Date"] = formatdate(time.time(), localtime=True)
        self.envelope_obj["Message-ID"] = self.msg_id
        self.envelope_obj["To"] = ", ".join(str(r) for r in self.recipients)
        self.envelope_obj["From"] = sender

        if self.subject:
            self.envelope_obj["Subject"] = self.subject
        if self.cc:
            self.envelope_obj["Cc"] = ", ".join(str(r) for r in self.cc)
        if self.bcc:
            self.envelope_obj["Bcc"] = ", ".join(str(r) for r in self.bcc)
        if self.reply_to:
            self.envelope_obj["Reply-To"] = ", ".join(str(r) for r in self.reply_to)

        if self.attachments:
            await self.attach_file(self.envelope_obj, self.attachments)

        if self.headers:
            for header_name, header_val in self.headers.items():
                self.envelope_obj.add_header(header_name, header_val)

        return self.envelope_obj
""",
        "function": "mime_message_builder_attachments",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "fastapi_mail/msg.py",
    },
    # ── 5. Async send message via SMTP session ───────────────────────────
    {
        "normalized_code": """\
from typing import Optional, Union
from jinja2 import Environment, Template
from fastapi_mail.config import XxxConfig
from fastapi_mail.connection import XxxConnection
from fastapi_mail.msg import MailMsg
from fastapi_mail.schemas import XxxSchema


class XxxMail:
    \"\"\"FastAPI mail dispatcher.\"\"\"

    def __init__(self, config: XxxConfig) -> None:
        self.config = config

    async def get_mail_template(
        self, env: Environment, template_name: str
    ) -> Template:
        \"\"\"Load Jinja2 template by name.\"\"\"
        return env.get_template(template_name)

    async def _prepare_message(
        self, envelope: XxxSchema, template: Optional[Template] = None
    ) -> Any:
        \"\"\"Prepare MIME envelope from schema.\"\"\"
        if template and envelope.template_body is not None:
            envelope.template_body = await self._render_template(
                envelope, template
            )
        msg = MailMsg(envelope)
        sender = await self._get_sender(envelope)
        return await msg._build_mime(sender)

    async def _render_template(
        self, envelope: XxxSchema, template: Template
    ) -> str:
        \"\"\"Render Jinja2 template with envelope data.\"\"\"
        data = envelope.template_body
        if isinstance(data, list):
            return template.render({"body": data})
        elif isinstance(data, dict):
            return template.render(**data)
        else:
            return template.render({"body": data})

    async def _get_sender(self, envelope: XxxSchema) -> str:
        \"\"\"Get sender address with optional name.\"\"\"
        from email.utils import formataddr
        addr = envelope.sender_addr or self.config.sender_addr
        name = envelope.sender_name or self.config.sender_name
        if name:
            return formataddr((name, addr))
        return addr

    async def send_message(
        self,
        envelope: Union[XxxSchema, list[XxxSchema]],
        template_name: Optional[str] = None,
    ) -> None:
        \"\"\"Send email envelope(s) via SMTP.\"\"\"
        envelopes = envelope if isinstance(envelope, list) else [envelope]
        prepared_envelopes = []

        template_env = None
        template_obj = None
        if self.config.template_dir and template_name:
            template_env = self.config.template_engine()
            template_obj = await self.get_mail_template(template_env, template_name)

        for env in envelopes:
            prepared = await self._prepare_message(env, template_obj)
            prepared_envelopes.append(prepared)

        async with XxxConnection(self.config) as session:
            if not self.config.suppress_send:
                for prepared in prepared_envelopes:
                    await session.session.send_message(prepared)
""",
        "function": "fastmail_async_send_message",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "fastapi_mail/fastmail.py",
    },
    # ── 6. Bulk email dispatch (multiple recipients, single connection) ────
    {
        "normalized_code": """\
from typing import List, Union
from fastapi_mail.schemas import XxxSchema


async def send_bulk_envelopes(
    mail_dispatcher: "XxxMail",
    envelopes: List[XxxSchema],
    reuse_connection: bool = True,
) -> None:
    \"\"\"Send multiple envelopes in single SMTP session.

    Args:
        mail_dispatcher: XxxMail instance
        envelopes: list of XxxSchema envelope objects
        reuse_connection: if True, all envelopes sent via single connection

    Returns:
        None
    \"\"\"
    if not envelopes:
        raise ValueError("envelopes list is empty")

    prepared_envelopes = []
    for envelope in envelopes:
        prepared = await mail_dispatcher._prepare_message(envelope)
        prepared_envelopes.append(prepared)

    if reuse_connection:
        async with mail_dispatcher.config.get_connection() as session:
            for prepared in prepared_envelopes:
                await session.session.send_message(prepared)
    else:
        for prepared in prepared_envelopes:
            async with mail_dispatcher.config.get_connection() as session:
                await session.session.send_message(prepared)
""",
        "function": "bulk_email_dispatch_single_connection",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "fastapi_mail/fastmail.py",
    },
    # ── 7. HTML + Plain text alternative message (multipart/alternative) ──
    {
        "normalized_code": """\
from typing import Optional
from jinja2 import Environment, Template
from email.mime.multipart import MIMEMultipart
from fastapi_mail.schemas import XxxSchema, MessageType, MultipartSubtypeEnum


async def prepare_html_and_plain_message(
    mail_dispatcher: "XxxMail",
    envelope: XxxSchema,
    html_template_name: str,
    plain_template_name: str,
) -> Any:
    \"\"\"Build envelope with both HTML and plain text alternatives.\"\"\"
    template_env = mail_dispatcher.config.template_engine()
    html_tpl = await mail_dispatcher.get_mail_template(template_env, html_template_name)
    plain_tpl = await mail_dispatcher.get_mail_template(template_env, plain_template_name)

    template_data = envelope.template_body
    if isinstance(template_data, list):
        template_data = {"body": template_data}
    elif not isinstance(template_data, dict):
        template_data = {"body": template_data}

    html_rendered = html_tpl.render(**template_data)
    plain_rendered = plain_tpl.render(**template_data)

    envelope.multipart_subtype = MultipartSubtypeEnum.alternative
    if envelope.subtype == MessageType.html:
        envelope.template_body = html_rendered
        envelope.alternative_body = plain_rendered
    else:
        envelope.template_body = plain_rendered
        envelope.alternative_body = html_rendered

    from fastapi_mail.msg import MailMsg
    msg = MailMsg(envelope)
    sender = await mail_dispatcher._get_sender(envelope)
    return await msg._build_mime(sender)
""",
        "function": "html_plain_text_alternative_multipart",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "fastapi_mail/fastmail.py",
    },
    # ── 8. Email validation (format, MX records, disposable check) ────────
    {
        "normalized_code": """\
import dns.resolver
from typing import Any, Dict, List, Optional, Union
from email_validator import validate_email, EmailNotValidError


class XxxEmailChecker:
    \"\"\"Email address validation and deliverability checks.\"\"\"

    def __init__(self) -> None:
        self.blocked_domains: set = set()
        self.blocked_addresses: set = set()
        self.temp_email_domains: list = []

    def validate_format(self, addr: str) -> bool:
        \"\"\"Validate email format per RFC.\"\"\"
        try:
            validated = validate_email(addr, check_deliverability=False)
            return True
        except EmailNotValidError:
            return False

    async def check_mx_record(self, domain: str) -> bool:
        \"\"\"Check if domain has MX records.\"\"\"
        try:
            mx_records = dns.resolver.resolve(domain, "MX")
            return True
        except (
            dns.resolver.NXDOMAIN,
            dns.resolver.NoAnswer,
            dns.resolver.NoNameservers,
        ):
            return False

    async def is_disposable(self, addr: str) -> bool:
        \"\"\"Check if address is temporary email.\"\"\"
        if not self.validate_format(addr):
            return False
        _, domain = addr.split("@")
        return domain in self.temp_email_domains

    async def is_blocked(self, addr: str) -> bool:
        \"\"\"Check if address is blacklisted.\"\"\"
        return addr in self.blocked_addresses

    async def add_blocked_domain(self, domain: str) -> None:
        \"\"\"Add domain to blacklist.\"\"\"
        self.blocked_domains.add(domain)

    async def add_blocked_address(self, addr: str) -> None:
        \"\"\"Add address to blacklist.\"\"\"
        if self.validate_format(addr):
            self.blocked_addresses.add(addr)
""",
        "function": "email_validation_mx_disposable_check",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "fastapi_mail/email_utils/email_check.py",
    },
    # ── 9. Signal dispatch after send (blinker event system) ────────────
    {
        "normalized_code": """\
from contextlib import contextmanager
import blinker


signals = blinker.Namespace()
envelope_dispatched = signals.signal(
    "envelope-dispatched",
    doc="Signal emitted after email sent (including test mode)."
)


class _XxxMailMixin:
    \"\"\"Mixin for email dispatch signals.\"\"\"

    @contextmanager
    def record_envelopes(self):
        \"\"\"Context manager to capture sent envelopes in tests.\"\"\"
        if not envelope_dispatched:
            raise RuntimeError("blinker required for signal recording")

        outbox = []

        def _record(envelope):
            outbox.append(envelope)

        envelope_dispatched.connect(_record)

        try:
            yield outbox
        finally:
            envelope_dispatched.disconnect(_record)


async def emit_dispatch_signal(envelope: Any) -> None:
    \"\"\"Emit signal after envelope sent.\"\"\"
    envelope_dispatched.send(envelope)
""",
        "function": "blinker_signal_dispatch_test_outbox",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "fastapi_mail/fastmail.py",
    },
    # ── 10. Background task email sending (asyncio task spawn) ───────────
    {
        "normalized_code": """\
import asyncio
from typing import Optional


async def send_envelope_background(
    mail_dispatcher: "XxxMail",
    envelope: "XxxSchema",
    template_name: Optional[str] = None,
    delay_seconds: float = 0,
) -> None:
    \"\"\"Send email in background job.\"\"\"
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)

    await mail_dispatcher.send_message(envelope, template_name=template_name)


def spawn_background_send(
    mail_dispatcher: "XxxMail",
    envelope: "XxxSchema",
    template_name: Optional[str] = None,
) -> asyncio.Task:
    \"\"\"Spawn background email send job (non-blocking).\"\"\"
    coroutine = asyncio.create_task(
        send_envelope_background(mail_dispatcher, envelope, template_name)
    )
    return coroutine
""",
        "function": "background_task_async_email_send",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "fastapi_mail/fastmail.py",
    },
    # ── 11. Retry logic with exponential backoff (error handling) ────────
    {
        "normalized_code": """\
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def send_with_retry(
    mail_dispatcher: "XxxMail",
    envelope: "XxxSchema",
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    template_name: Optional[str] = None,
) -> bool:
    \"\"\"Send email with exponential backoff retry.\"\"\"
    attempt = 0
    delay = 1.0

    while attempt < max_retries:
        try:
            await mail_dispatcher.send_message(
                envelope, template_name=template_name
            )
            logger.info(f"Email sent to {envelope.recipients} on attempt {attempt + 1}")
            return True

        except Exception as error:
            attempt += 1
            if attempt < max_retries:
                logger.warning(
                    f"Send attempt {attempt} failed: {error}. "
                    f"Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
                delay *= backoff_factor
            else:
                logger.error(f"Email send failed after {max_retries} attempts: {error}")
                return False

    return False
""",
        "function": "retry_with_exponential_backoff_error_handling",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "fastapi_mail/fastmail.py",
    },
    # ── 12. Template data validation and sanitization ──────────────────
    {
        "normalized_code": """\
from typing import Any, Dict, List, Union
from pydantic import BaseModel, ConfigDict, field_validator


class TemplateDataXxx(BaseModel):
    \"\"\"Template context data validation.\"\"\"

    template_vars: Dict[str, Any] = {}
    charset: str = "utf-8"
    auto_escape: bool = True

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator("template_vars")
    @classmethod
    def validate_template_vars(cls, data: Dict) -> Dict:
        \"\"\"Ensure template vars are JSON-serializable.\"\"\"
        for key, val in data.items():
            if not isinstance(key, str):
                raise ValueError(f"template var key must be string, got {type(key)}")
            if isinstance(val, (str, int, float, bool, type(None))):
                continue
            elif isinstance(val, (list, dict)):
                continue
            else:
                raise ValueError(
                    f"template var '{key}' has non-JSON type {type(val)}"
                )
        return data

    def to_template_context(self) -> Dict[str, Any]:
        \"\"\"Convert to Jinja2 template context.\"\"\"
        return self.template_vars
""",
        "function": "template_data_validation_json_serializable",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "fastapi_mail/schemas.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "async SMTP connection aiosmtplib context manager",
    "email message schema Pydantic validation recipients attachments",
    "MIME multipart message building headers body charset",
    "send email via SMTP session async context",
    "bulk email dispatch multiple recipients single connection",
    "HTML plain text alternative multipart message",
    "email validation MX records disposable check",
    "signal dispatch blinker event system test outbox",
    "background asyncio task email sending",
    "retry exponential backoff error handling",
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
    print(f"  {len(PATTERNS)} patterns extracted")

    # Cleanup existing points for this tag
    cleanup(client)

    n_indexed = index_patterns(client, payloads)
    count_after = client.count(collection_name=COLLECTION).count
    print(f"  {n_indexed} patterns indexed — KB: {count_after} points")

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
        print("  DRY_RUN — data deleted")


if __name__ == "__main__":
    main()
