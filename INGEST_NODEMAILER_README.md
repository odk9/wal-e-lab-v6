# Ingestion: nodemailer/nodemailer

## Overview

**Repository:** https://github.com/nodemailer/nodemailer  
**Language:** JavaScript  
**Stack:** `javascript+nodemailer+smtp+email`  
**Patterns:** 12 core email transport patterns  
**Charte Version:** 1.0

## Pattern Coverage

| # | Function | Feature Type | Description |
|---|---|---|---|
| 1 | `create_smtp_transporter` | config | Create SMTP transport with auth |
| 2 | `send_mail_text_html_alternatives` | crud | Send mail with text/HTML alternatives |
| 3 | `attachment_handling_file_buffer_stream_url` | utility | Handle attachments (file, buffer, stream, data URL) |
| 4 | `embedded_images_cid_html_template` | utility | Embed images via Content-ID (CID) |
| 5 | `oauth2_xoauth2_auth_refresh_token` | dependency | OAuth2 XOAUTH2 authentication |
| 6 | `dkim_signing_outgoing_messages` | dependency | DKIM signing of messages |
| 7 | `smtp_connection_pooling_max_connections` | config | SMTP connection pooling |
| 8 | `address_parsing_validation_to_cc_bcc` | utility | Parse & validate email addresses |
| 9 | `stream_based_transport_large_attachments` | config | Stream-based transport for large attachments |
| 10 | `verify_smtp_connection_test` | utility | Verify SMTP connection |
| 11 | `mail_composer_mime_multipart_tree` | utility | MIME tree composition (multipart) |
| 12 | `custom_headers_message_metadata` | utility | Custom headers & message metadata |

## Normalization (Charte Wal-e V1.0)

All patterns comply with **Charte Wal-e** rules:

- **U-5:** Entity names normalized (no domain-specific entities like `user`, `message`, `task`, etc.)
  - `message` → `envelope`, `mailOptions`
  - `user` → `username`, `authConfig`
  - Kept domain terms: `transporter`, `smtp`, `attachment`, `html`, `text`, `subject`, `from`, `to`, `cc`, `bcc`, `dkim`, `oauth2`, `mime`, `cid`

- **J-1/J-2/J-3:** No `var`, no callback hell, no `console.log()`
- **U-2:** All imports are used
- **U-3:** All parameters are typed
- **U-6:** Functions kept under 40 lines

## Usage

### Run in DRY_RUN mode (preview only)

```bash
cd "Wal-e Lab V6"
.venv/bin/python3 ingest_nodemailer.py
# DRY_RUN=True in script — data is indexed then deleted
```

### Run in PRODUCTION mode (persist to KB)

Edit `ingest_nodemailer.py`:
```python
DRY_RUN = True  # change to False
```

Then:
```bash
.venv/bin/python3 ingest_nodemailer.py
```

## Audit Results (DRY_RUN)

```
Patterns indexed : 12
KB initial       : 745 points
KB after         : 757 points
Violations       : 0 ✅
Verdict          : ✅ PASS
```

All 12 audit queries matched their corresponding patterns with scores 0.49–0.77.

## Files

- `/sessions/sweet-practical-fermi/mnt/Wal-e Lab V6/ingest_nodemailer.py` — Main ingestion script
- `/sessions/sweet-practical-fermi/mnt/Wal-e Lab V6/kb_utils.py` — Shared utilities (validation, payload building)
- `/sessions/sweet-practical-fermi/mnt/Wal-e Lab V6/embedder.py` — Embedding wrapper (fastembed)

## Technical Notes

- **Clone:** `git clone --depth 1 https://github.com/nodemailer/nodemailer.git /tmp/nodemailer`
- **KB Path:** `./kb_qdrant/` (Qdrant embedded, vector dim 768)
- **Embedding Model:** `nomic-ai/nomic-embed-text-v1.5-Q` (fastembed)
- **Collection:** `patterns` (indexed by `language`, `framework`, `feature_type`, `file_role`)

## Next Steps

1. Run script in PRODUCTION mode to persist patterns to KB
2. Query patterns using `query_kb()` with `language="javascript"`
3. Use retrieved patterns to scaffold JavaScript email applications
4. Extend with additional email transport patterns (SendGrid, SES, Mailgun)
