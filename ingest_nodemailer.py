"""
ingest_nodemailer.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de nodemailer/nodemailer dans la KB Qdrant V6.

Focus : CORE patterns email transport (SMTP transporter creation, send mail with
attachments, OAuth2 XOAUTH2 auth, DKIM signing, connection pooling, address parsing,
embedded images via CID, stream-based sending).

Usage:
    .venv/bin/python3 ingest_nodemailer.py
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
REPO_URL = "https://github.com/nodemailer/nodemailer.git"
REPO_NAME = "nodemailer/nodemailer"
REPO_LOCAL = "/tmp/nodemailer"
LANGUAGE = "javascript"
FRAMEWORK = "generic"
STACK = "javascript+nodemailer+smtp+email"
CHARTE_VERSION = "1.0"
TAG = "nodemailer/nodemailer"
SOURCE_REPO = "https://github.com/nodemailer/nodemailer"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Nodemailer = Email transport library (SMTP, Sendmail, Stream, SES, JSON).
# Patterns CORE : transporter creation, mail composition, attachment handling,
# authentication (OAuth2, DKIM), stream-based sending.
# U-5 : message → envelope, user → username, task → job, etc.

PATTERNS: list[dict] = [
    # ── 1. Create SMTP transport with config object ──────────────────────────
    {
        "normalized_code": """\
'use strict';

const SMTPTransport = require('./smtp-transport');

function createTransport(options) {
    const config = {
        host: options.host,
        port: options.port || 587,
        secure: options.secure || false,
        auth: {
            username: options.username,
            password: options.password,
        },
        tls: {
            rejectUnauthorized: options.rejectUnauthorized !== false,
        }
    };
    return new SMTPTransport(config);
}

module.exports = { createTransport };
""",
        "function": "create_smtp_transporter",
        "feature_type": "config",
        "file_role": "route",
    },
    # ── 2. Send mail with text and HTML alternatives ────────────────────────
    {
        "normalized_code": """\
'use strict';

async function sendMail(transporter, envelope) {
    const mailOptions = {
        from: envelope.from,
        to: envelope.to,
        cc: envelope.cc,
        bcc: envelope.bcc,
        subject: envelope.subject,
        text: envelope.text,
        html: envelope.html,
        headers: envelope.headers || {},
        messageId: envelope.messageId,
        inReplyTo: envelope.inReplyTo,
        references: envelope.references,
    };
    return transporter.sendMail(mailOptions);
}

module.exports = { sendMail };
""",
        "function": "send_mail_text_html_alternatives",
        "feature_type": "crud",
        "file_role": "route",
    },
    # ── 3. Attachment handling: file, buffer, stream, data URL ───────────────
    {
        "normalized_code": """\
'use strict';

const fs = require('fs');

function buildAttachments(attachmentList) {
    return attachmentList.map((element) => {
        const attachment = {
            filename: element.filename,
            contentType: element.contentType,
        };
        if (element.path) {
            attachment.path = element.path;
        } else if (element.content) {
            attachment.content = element.content;
        } else if (element.stream) {
            attachment.content = element.stream;
        } else if (element.href) {
            attachment.href = element.href;
        }
        if (element.cid) {
            attachment.cid = element.cid;
        }
        if (element.contentDisposition) {
            attachment.contentDisposition = element.contentDisposition;
        }
        return attachment;
    });
}

module.exports = { buildAttachments };
""",
        "function": "attachment_handling_file_buffer_stream_url",
        "feature_type": "utility",
        "file_role": "utility",
    },
    # ── 4. Embedded images via Content-ID (CID) for HTML ────────────────────
    {
        "normalized_code": """\
'use strict';

function createHtmlWithEmbedded(htmlTemplate, imageList) {
    let html = htmlTemplate;
    imageList.forEach((image) => {
        const placeholder = `cid:${image.cid}`;
        const srcAttr = `src="${placeholder}"`;
        html = html.replace(`src="${image.cid}"`, srcAttr);
    });
    return html;
}

function sendMailWithEmbedded(transporter, envelope, attachmentList) {
    const mailOptions = {
        from: envelope.from,
        to: envelope.to,
        subject: envelope.subject,
        html: createHtmlWithEmbedded(envelope.html, attachmentList),
        attachments: attachmentList.map((image) => ({
            filename: image.filename,
            path: image.path,
            cid: image.cid,
            contentDisposition: 'inline',
        })),
    };
    return transporter.sendMail(mailOptions);
}

module.exports = { sendMailWithEmbedded };
""",
        "function": "embedded_images_cid_html_template",
        "feature_type": "utility",
        "file_role": "utility",
    },
    # ── 5. OAuth2 XOAUTH2 authentication with refresh token ─────────────────
    {
        "normalized_code": """\
'use strict';

const XOAuth2 = require('./xoauth2');

function setupOAuth2Auth(authConfig) {
    const oauth2 = new XOAuth2({
        user: authConfig.user,
        clientId: authConfig.clientId,
        clientSecret: authConfig.clientSecret,
        refreshToken: authConfig.refreshToken,
        accessToken: authConfig.accessToken,
        expires: authConfig.expires,
        timeout: authConfig.timeout,
    });
    return oauth2;
}

function createTransporterWithOAuth2(host, port, oauth2) {
    return {
        host: host,
        port: port || 587,
        secure: false,
        auth: oauth2,
    };
}

module.exports = { setupOAuth2Auth, createTransporterWithOAuth2 };
""",
        "function": "oauth2_xoauth2_auth_refresh_token",
        "feature_type": "dependency",
        "file_role": "utility",
    },
    # ── 6. DKIM signing of outgoing messages ──────────────────────────────────
    {
        "normalized_code": """\
'use strict';

const DKIM = require('./dkim');

function setupDKIMSigning(dkimConfig) {
    const dkimSigner = new DKIM({
        domainName: dkimConfig.domainName,
        keySelector: dkimConfig.keySelector,
        privateKey: dkimConfig.privateKey,
        cacheDir: dkimConfig.cacheDir,
    });
    return dkimSigner;
}

function applyDKIMToMail(mail, dkimSigner) {
    if (dkimSigner) {
        mail.dkim = dkimSigner;
    }
    return mail;
}

module.exports = { setupDKIMSigning, applyDKIMToMail };
""",
        "function": "dkim_signing_outgoing_messages",
        "feature_type": "dependency",
        "file_role": "utility",
    },
    # ── 7. SMTP connection pooling (max connections, max messages) ──────────
    {
        "normalized_code": """\
'use strict';

const SMTPPool = require('./smtp-pool');

function createSMTPPool(options) {
    const poolConfig = {
        host: options.host,
        port: options.port || 587,
        secure: options.secure || false,
        auth: {
            username: options.username,
            password: options.password,
        },
        maxConnections: options.maxConnections || 5,
        maxMessages: options.maxMessages || 100,
        rateDelta: options.rateDelta || 1000,
        rateLimit: options.rateLimit || 0,
        connectionUrl: options.connectionUrl,
    };
    return new SMTPPool(poolConfig);
}

module.exports = { createSMTPPool };
""",
        "function": "smtp_connection_pooling_max_connections",
        "feature_type": "config",
        "file_role": "utility",
    },
    # ── 8. Address parsing and validation (to, cc, bcc) ────────────────────
    {
        "normalized_code": """\
'use strict';

const addressparser = require('./addressparser');

function parseRecipients(recipientString) {
    if (!recipientString) {
        return [];
    }
    if (Array.isArray(recipientString)) {
        return recipientString;
    }
    return addressparser(recipientString);
}

function validateAddresses(envelope) {
    const recipients = []
        .concat(parseRecipients(envelope.to) || [])
        .concat(parseRecipients(envelope.cc) || [])
        .concat(parseRecipients(envelope.bcc) || []);

    const invalid = recipients.filter(
        (addr) => !addr.address || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(addr.address)
    );

    if (invalid.length > 0) {
        throw new Error(`Invalid addresses: ${invalid.map((a) => a.address).join(', ')}`);
    }
    return recipients;
}

module.exports = { parseRecipients, validateAddresses };
""",
        "function": "address_parsing_validation_to_cc_bcc",
        "feature_type": "utility",
        "file_role": "utility",
    },
    # ── 9. Stream-based transport for large attachments ─────────────────────
    {
        "normalized_code": """\
'use strict';

const { PassThrough } = require('stream');
const StreamTransport = require('./stream-transport');

function createStreamTransport(options) {
    const streamConfig = {
        streamTransport: true,
        newline: options.newline || 'unix',
        logger: options.logger || false,
    };
    return new StreamTransport(streamConfig);
}

async function sendViaStream(transporter, envelope) {
    const stream = await transporter.sendMail({
        from: envelope.from,
        to: envelope.to,
        subject: envelope.subject,
        text: envelope.text,
        attachments: envelope.attachments || [],
    });
    return new Promise((resolve, reject) => {
        stream.on('finish', resolve);
        stream.on('error', reject);
    });
}

module.exports = { createStreamTransport, sendViaStream };
""",
        "function": "stream_based_transport_large_attachments",
        "feature_type": "config",
        "file_role": "utility",
    },
    # ── 10. Connection verification (verify SMTP connection) ─────────────────
    {
        "normalized_code": """\
'use strict';

async function verifySMTPConnection(transporter) {
    try {
        await transporter.verify();
        return {
            success: true,
            message: 'SMTP connection verified',
        };
    } catch (error) {
        return {
            success: false,
            error: error.message,
            code: error.code,
        };
    }
}

async function testConnection(envelope) {
    const transporter = require('nodemailer').createTransport(envelope);
    return verifySMTPConnection(transporter);
}

module.exports = { verifySMTPConnection, testConnection };
""",
        "function": "verify_smtp_connection_test",
        "feature_type": "utility",
        "file_role": "utility",
    },
    # ── 11. Mail composer: MIME tree construction (multipart, alternatives) ─
    {
        "normalized_code": """\
'use strict';

const MailComposer = require('./mail-composer');

function composeMessage(envelope) {
    const composer = new MailComposer(envelope);
    const mimeMessage = composer.compile();
    return mimeMessage;
}

function buildMimeEnvelope(envelope) {
    const options = {
        from: envelope.from,
        to: envelope.to,
        cc: envelope.cc,
        bcc: envelope.bcc,
        subject: envelope.subject,
        text: envelope.text,
        html: envelope.html,
        attachments: envelope.attachments || [],
        headers: envelope.headers || {},
        priority: envelope.priority || 'normal',
        envelope: {
            from: envelope.envelopeFrom,
            to: envelope.envelopeTo,
        },
    };
    return composeMessage(options);
}

module.exports = { composeMessage, buildMimeEnvelope };
""",
        "function": "mail_composer_mime_multipart_tree",
        "feature_type": "utility",
        "file_role": "utility",
    },
    # ── 12. Custom headers and message metadata ────────────────────────────
    {
        "normalized_code": """\
'use strict';

function buildMailWithMetadata(envelope) {
    const mailOptions = {
        from: envelope.from,
        to: envelope.to,
        subject: envelope.subject,
        text: envelope.text,
        html: envelope.html,
        messageId: envelope.messageId,
        date: envelope.date,
        inReplyTo: envelope.inReplyTo,
        references: envelope.references,
        priority: envelope.priority || 'normal',
        headers: {},
    };
    if (envelope.customHeaders) {
        Object.assign(mailOptions.headers, envelope.customHeaders);
    }
    if (envelope.replyTo) {
        mailOptions.replyTo = envelope.replyTo;
    }
    if (envelope.sender) {
        mailOptions.sender = envelope.sender;
    }
    if (envelope.dsn) {
        mailOptions.dsn = envelope.dsn;
    }
    return mailOptions;
}

module.exports = { buildMailWithMetadata };
""",
        "function": "custom_headers_message_metadata",
        "feature_type": "utility",
        "file_role": "utility",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "create SMTP transport with authentication",
    "send email with text and HTML alternatives",
    "handle attachments file buffer stream data URL",
    "embed images in HTML via Content-ID CID",
    "OAuth2 authentication with refresh token XOAUTH2",
    "DKIM sign outgoing email messages",
    "SMTP connection pooling max connections messages",
    "parse and validate email addresses recipients",
    "stream-based transport for large attachments",
    "verify SMTP connection test",
    "MIME tree composition multipart alternatives",
    "custom headers message metadata priority",
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
                file_path="lib/nodemailer.js",
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
