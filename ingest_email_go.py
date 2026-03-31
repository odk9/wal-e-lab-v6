"""
ingest_email_go.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
du package jordan-wright/email (Go email library) dans la KB Qdrant V6.

Focus : CORE patterns email building/sending (Email struct, SMTP send, attachments,
MIME multipart, TLS/STARTTLS, connection pool, parsing from io.Reader).

NOT patterns CRUD/API — patterns de construction et transmission d'emails.

Usage:
    .venv/bin/python3 ingest_email_go.py
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
REPO_URL = "https://github.com/jordan-wright/email.git"
REPO_NAME = "jordan-wright/email"
REPO_LOCAL = "/tmp/email"
LANGUAGE = "go"
FRAMEWORK = "generic"
STACK = "go+email+smtp"
CHARTE_VERSION = "1.0"
TAG = "jordan-wright/email"
SOURCE_REPO = "https://github.com/jordan-wright/email"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Go email library = building and sending emails via SMTP.
# U-5 replacements:
#   user → xxx
#   message → envelope
#   event → signal
#   tag → label
#   order → sequence
#   item → element
#   task → job
#   post → entry
#   comment → annotation
#   (keep: Email, Pool, SMTP, TLS, Attachment, From, To, Subject, Text, HTML, MIME, Auth, PlainAuth)

PATTERNS: list[dict] = [
    # ── 1. Email struct creation with headers ─────────────────────────────
    {
        "normalized_code": """\
import (
\t"net/textproto"
)

type Email struct {
\tReplyTo     []string
\tFrom        string
\tTo          []string
\tBcc         []string
\tCc          []string
\tSubject     string
\tText        []byte
\tHTML        []byte
\tSender      string
\tHeaders     textproto.MIMEHeader
\tAttachments []*Attachment
\tReadReceipt []string
}

func NewEmail() *Email {
\treturn &Email{Headers: textproto.MIMEHeader{}}
}
""",
        "function": "email_struct_creation_with_headers",
        "feature_type": "schema",
        "file_role": "model",
        "file_path": "email.go",
    },
    # ── 2. Email struct → bytes conversion (MIME rendering) ──────────────
    {
        "normalized_code": """\
import (
\t"bytes"
\t"io"
\t"mime/multipart"
\t"net/textproto"
)

func (e *Email) Bytes() ([]byte, error) {
\tbuff := bytes.NewBuffer(make([]byte, 0, 4096))
\theaders, err := e.msgHeaders()
\tif err != nil {
\t\treturn nil, err
\t}
\thtmlAttachments, otherAttachments := e.categorizeAttachments()
\tif len(e.HTML) == 0 && len(htmlAttachments) > 0 {
\t\treturn nil, errors.New("there are HTML attachments, but no HTML body")
\t}

\tvar (
\t\tisMixed       = len(otherAttachments) > 0
\t\tisAlternative = len(e.Text) > 0 && len(e.HTML) > 0
\t\tisRelated     = len(e.HTML) > 0 && len(htmlAttachments) > 0
\t)

\tvar w *multipart.Writer
\tif isMixed || isAlternative || isRelated {
\t\tw = multipart.NewWriter(buff)
\t}
\tswitch {
\tcase isMixed:
\t\theaders.Set("Content-Type", "multipart/mixed;\\r\\n boundary="+w.Boundary())
\tcase isAlternative:
\t\theaders.Set("Content-Type", "multipart/alternative;\\r\\n boundary="+w.Boundary())
\tcase isRelated:
\t\theaders.Set("Content-Type", "multipart/related;\\r\\n boundary="+w.Boundary())
\tcase len(e.HTML) > 0:
\t\theaders.Set("Content-Type", "text/html; charset=UTF-8")
\tdefault:
\t\theaders.Set("Content-Type", "text/plain; charset=UTF-8")
\t}

\theaderToBytes(buff, headers)
\t_, err = io.WriteString(buff, "\\r\\n")
\tif err != nil {
\t\treturn nil, err
\t}

\treturn buff.Bytes(), nil
}
""",
        "function": "email_to_bytes_mime_rendering",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "email.go",
    },
    # ── 3. Attachment struct and header setup ──────────────────────────
    {
        "normalized_code": """\
import (
\t"fmt"
\t"net/textproto"
)

type Attachment struct {
\tFilename    string
\tContentType string
\tHeader      textproto.MIMEHeader
\tContent     []byte
\tHTMLRelated bool
}

func (at *Attachment) setDefaultHeaders() {
\tcontentType := "application/octet-stream"
\tif len(at.ContentType) > 0 {
\t\tcontentType = at.ContentType
\t}
\tat.Header.Set("Content-Type", contentType)

\tif len(at.Header.Get("Content-Disposition")) == 0 {
\t\tdisposition := "attachment"
\t\tif at.HTMLRelated {
\t\t\tdisposition = "inline"
\t\t}
\t\tat.Header.Set("Content-Disposition", fmt.Sprintf("%s;\\r\\n filename=\\"%s\\"", disposition, at.Filename))
\t}
\tif len(at.Header.Get("Content-ID")) == 0 {
\t\tat.Header.Set("Content-ID", fmt.Sprintf("<%s>", at.Filename))
\t}
\tif len(at.Header.Get("Content-Transfer-Encoding")) == 0 {
\t\tat.Header.Set("Content-Transfer-Encoding", "base64")
\t}
}
""",
        "function": "attachment_struct_and_headers",
        "feature_type": "schema",
        "file_role": "model",
        "file_path": "email.go",
    },
    # ── 4. Attach file or io.Reader to email ──────────────────────────
    {
        "normalized_code": """\
import (
\t"bytes"
\t"io"
\t"mime"
\t"os"
\t"path/filepath"
)

func (e *Email) Attach(r io.Reader, filename string, c string) (a *Attachment, err error) {
\tvar buffer bytes.Buffer
\tif _, err = io.Copy(&buffer, r); err != nil {
\t\treturn
\t}
\tat := &Attachment{
\t\tFilename:    filename,
\t\tContentType: c,
\t\tHeader:      textproto.MIMEHeader{},
\t\tContent:     buffer.Bytes(),
\t}
\te.Attachments = append(e.Attachments, at)
\treturn at, nil
}

func (e *Email) AttachFile(filename string) (a *Attachment, err error) {
\tf, err := os.Open(filename)
\tif err != nil {
\t\treturn
\t}
\tdefer f.Close()

\tct := mime.TypeByExtension(filepath.Ext(filename))
\tbasename := filepath.Base(filename)
\treturn e.Attach(f, basename, ct)
}
""",
        "function": "attach_file_or_reader",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "email.go",
    },
    # ── 5. Send email via SMTP with Auth ──────────────────────────────
    {
        "normalized_code": """\
import (
\t"errors"
\t"net/mail"
\t"net/smtp"
)

func (e *Email) Send(addr string, a smtp.Auth) error {
\tto := make([]string, 0, len(e.To)+len(e.Cc)+len(e.Bcc))
\tto = append(append(append(to, e.To...), e.Cc...), e.Bcc...)
\tfor i := 0; i < len(to); i++ {
\t\taddr, err := mail.ParseAddress(to[i])
\t\tif err != nil {
\t\t\treturn err
\t\t}
\t\tto[i] = addr.Address
\t}

\tif e.From == "" || len(to) == 0 {
\t\treturn errors.New("Must specify at least one From address and one To address")
\t}

\tsender, err := e.parseSender()
\tif err != nil {
\t\treturn err
\t}

\traw, err := e.Bytes()
\tif err != nil {
\t\treturn err
\t}

\treturn smtp.SendMail(addr, a, sender, to, raw)
}

func (e *Email) parseSender() (string, error) {
\tif e.Sender != "" {
\t\tsender, err := mail.ParseAddress(e.Sender)
\t\tif err != nil {
\t\t\treturn "", err
\t\t}
\t\treturn sender.Address, nil
\t} else {
\t\tfrom, err := mail.ParseAddress(e.From)
\t\tif err != nil {
\t\t\treturn "", err
\t\t}
\t\treturn from.Address, nil
\t}
}
""",
        "function": "send_email_via_smtp_auth",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "email.go",
    },
    # ── 6. Send email with TLS (explicit STARTTLS) ────────────────────
    {
        "normalized_code": """\
import (
\t"crypto/tls"
\t"errors"
\t"net/mail"
\t"net/smtp"
)

func (e *Email) SendWithStartTLS(addr string, a smtp.Auth, t *tls.Config) error {
\tto := make([]string, 0, len(e.To)+len(e.Cc)+len(e.Bcc))
\tto = append(append(append(to, e.To...), e.Cc...), e.Bcc...)
\tfor i := 0; i < len(to); i++ {
\t\taddr, err := mail.ParseAddress(to[i])
\t\tif err != nil {
\t\t\treturn err
\t\t}
\t\tto[i] = addr.Address
\t}

\tif e.From == "" || len(to) == 0 {
\t\treturn errors.New("Must specify at least one From address and one To address")
\t}

\tsender, err := e.parseSender()
\tif err != nil {
\t\treturn err
\t}

\traw, err := e.Bytes()
\tif err != nil {
\t\treturn err
\t}

\tc, err := smtp.Dial(addr)
\tif err != nil {
\t\treturn err
\t}
\tdefer c.Close()

\tif err = c.Hello("localhost"); err != nil {
\t\treturn err
\t}

\tif ok, _ := c.Extension("STARTTLS"); ok {
\t\tif err = c.StartTLS(t); err != nil {
\t\t\treturn err
\t\t}
\t}

\tif a != nil {
\t\tif ok, _ := c.Extension("AUTH"); ok {
\t\t\tif err = c.Auth(a); err != nil {
\t\t\t\treturn err
\t\t\t}
\t\t}
\t}

\tif err = c.Mail(sender); err != nil {
\t\treturn err
\t}

\tfor _, addr := range to {
\t\tif err = c.Rcpt(addr); err != nil {
\t\t\treturn err
\t\t}
\t}

\tw, err := c.Data()
\tif err != nil {
\t\treturn err
\t}

\t_, err = w.Write(raw)
\tif err != nil {
\t\treturn err
\t}

\tret err = w.Close()
\tif err != nil {
\t\treturn err
\t}

\treturn c.Quit()
}
""",
        "function": "send_email_with_starttls_tls",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "email.go",
    },
    # ── 7. Send email with explicit TLS (dial TLS first) ──────────────
    {
        "normalized_code": """\
import (
\t"crypto/tls"
\t"errors"
\t"net/mail"
\t"net/smtp"
)

func (e *Email) SendWithTLS(addr string, a smtp.Auth, t *tls.Config) error {
\tto := make([]string, 0, len(e.To)+len(e.Cc)+len(e.Bcc))
\tto = append(append(append(to, e.To...), e.Cc...), e.Bcc...)
\tfor i := 0; i < len(to); i++ {
\t\taddr, err := mail.ParseAddress(to[i])
\t\tif err != nil {
\t\t\treturn err
\t\t}
\t\tto[i] = addr.Address
\t}

\tif e.From == "" || len(to) == 0 {
\t\treturn errors.New("Must specify at least one From address and one To address")
\t}

\tsender, err := e.parseSender()
\tif err != nil {
\t\treturn err
\t}

\traw, err := e.Bytes()
\tif err != nil {
\t\treturn err
\t}

\tconn, err := tls.Dial("tcp", addr, t)
\tif err != nil {
\t\treturn err
\t}

\tc, err := smtp.NewClient(conn, t.ServerName)
\tif err != nil {
\t\treturn err
\t}
\tdefer c.Close()

\tif err = c.Hello("localhost"); err != nil {
\t\treturn err
\t}

\tif a != nil {
\t\tif ok, _ := c.Extension("AUTH"); ok {
\t\t\tif err = c.Auth(a); err != nil {
\t\t\t\treturn err
\t\t\t}
\t\t}
\t}

\tif err = c.Mail(sender); err != nil {
\t\treturn err
\t}

\tfor _, addr := range to {
\t\tif err = c.Rcpt(addr); err != nil {
\t\t\treturn err
\t\t}
\t}

\tw, err := c.Data()
\tif err != nil {
\t\treturn err
\t}

\t_, err = w.Write(raw)
\tif err != nil {
\t\treturn err
\t}

\terr = w.Close()
\tif err != nil {
\t\treturn err
\t}

\treturn c.Quit()
}
""",
        "function": "send_email_with_tls_explicit",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "email.go",
    },
    # ── 8. Parse email from io.Reader (RFC 5322 format) ───────────────
    {
        "normalized_code": """\
import (
\t"bufio"
\t"io"
\t"mime"
\t"mime/multipart"
\t"net/textproto"
\t"strings"
)

func NewEmailFromReader(r io.Reader) (*Email, error) {
\te := NewEmail()
\ts := &trimReader{rd: r}
\ttp := textproto.NewReader(bufio.NewReader(s))

\thdrs, err := tp.ReadMIMEHeader()
\tif err != nil {
\t\treturn e, err
\t}

\tfor h, v := range hdrs {
\t\tswitch h {
\t\tcase "Subject":
\t\t\te.Subject = v[0]
\t\t\tsubj, err := (&mime.WordDecoder{}).DecodeHeader(e.Subject)
\t\t\tif err == nil && len(subj) > 0 {
\t\t\t\te.Subject = subj
\t\t\t}
\t\t\tdelete(hdrs, h)
\t\tcase "To":
\t\t\te.To = handleAddressList(v)
\t\t\tdelete(hdrs, h)
\t\tcase "From":
\t\t\te.From = v[0]
\t\t\tfr, err := (&mime.WordDecoder{}).DecodeHeader(e.From)
\t\t\tif err == nil && len(fr) > 0 {
\t\t\t\te.From = fr
\t\t\t}
\t\t\tdelete(hdrs, h)
\t\tcase "Cc":
\t\t\te.Cc = handleAddressList(v)
\t\t\tdelete(hdrs, h)
\t\tcase "Bcc":
\t\t\te.Bcc = handleAddressList(v)
\t\t\tdelete(hdrs, h)
\t\tcase "Reply-To":
\t\t\te.ReplyTo = handleAddressList(v)
\t\t\tdelete(hdrs, h)
\t\t}
\t}

\te.Headers = hdrs
\tbody := tp.R

\tps, err := parseMIMEParts(e.Headers, body)
\tif err != nil {
\t\treturn e, err
\t}

\tfor _, p := range ps {
\t\tct, _, err := mime.ParseMediaType(p.header.Get("Content-Type"))
\t\tif err != nil {
\t\t\treturn e, err
\t\t}

\t\tswitch {
\t\tcase ct == "text/plain":
\t\t\te.Text = p.body
\t\tcase ct == "text/html":
\t\t\te.HTML = p.body
\t\t}
\t}

\treturn e, nil
}
""",
        "function": "parse_email_from_reader_rfc5322",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "email.go",
    },
    # ── 9. MIME multipart parsing (recursive) ────────────────────────
    {
        "normalized_code": """\
import (
\t"bytes"
\t"encoding/base64"
\t"io"
\t"mime"
\t"mime/multipart"
\t"net/textproto"
\t"strings"
)

func parseMIMEParts(hs textproto.MIMEHeader, b io.Reader) ([]*part, error) {
\tvar ps []*part

\tif _, ok := hs["Content-Type"]; !ok {
\t\ths.Set("Content-Type", "text/plain; charset=us-ascii")
\t}

\tct, params, err := mime.ParseMediaType(hs.Get("Content-Type"))
\tif err != nil {
\t\treturn ps, err
\t}

\tif strings.HasPrefix(ct, "multipart/") {
\t\tif _, ok := params["boundary"]; !ok {
\t\t\treturn ps, errors.New("No boundary found for multipart entity")
\t\t}

\t\tmr := multipart.NewReader(b, params["boundary"])
\t\tfor {
\t\t\tvar buf bytes.Buffer
\t\t\tp, err := mr.NextPart()
\t\t\tif err == io.EOF {
\t\t\t\tbreak
\t\t\t}
\t\t\tif err != nil {
\t\t\t\treturn ps, err
\t\t\t}

\t\t\tif _, ok := p.Header["Content-Type"]; !ok {
\t\t\t\tp.Header.Set("Content-Type", "text/plain; charset=us-ascii")
\t\t\t}

\t\t\tsubct, _, err := mime.ParseMediaType(p.Header.Get("Content-Type"))
\t\t\tif err != nil {
\t\t\t\treturn ps, err
\t\t\t}

\t\t\tif strings.HasPrefix(subct, "multipart/") {
\t\t\t\tsps, err := parseMIMEParts(p.Header, p)
\t\t\t\tif err != nil {
\t\t\t\t\treturn ps, err
\t\t\t\t}
\t\t\t\tps = append(ps, sps...)
\t\t\t} else {
\t\t\t\tvar reader io.Reader
\t\t\t\treader = p
\t\t\t\tconst cte = "Content-Transfer-Encoding"
\t\t\t\tif p.Header.Get(cte) == "base64" {
\t\t\t\t\treader = base64.NewDecoder(base64.StdEncoding, reader)
\t\t\t\t}
\t\t\t\tif _, err := io.Copy(&buf, reader); err != nil {
\t\t\t\t\treturn ps, err
\t\t\t\t}
\t\t\t\tps = append(ps, &part{body: buf.Bytes(), header: p.Header})
\t\t\t}
\t\t}
\t} else {
\t\tswitch hs.Get("Content-Transfer-Encoding") {
\t\tcase "base64":
\t\t\tb = base64.NewDecoder(base64.StdEncoding, b)
\t\t}

\t\tvar buf bytes.Buffer
\t\tif _, err := io.Copy(&buf, b); err != nil {
\t\t\treturn ps, err
\t\t}
\t\tps = append(ps, &part{body: buf.Bytes(), header: hs})
\t}

\treturn ps, nil
}
""",
        "function": "parse_mime_multipart_recursive",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "email.go",
    },
    # ── 10. Connection pool for bulk email sending ───────────────────
    {
        "normalized_code": """\
import (
\t"crypto/tls"
\t"net"
\t"net/smtp"
\t"sync"
\t"time"
)

type Pool struct {
\taddr          string
\tauth          smtp.Auth
\tmax           int
\tcreated       int
\tclients       chan *client
\trebuild       chan struct{}
\tmut           *sync.Mutex
\tlastBuildErr  *timestampedErr
\tclosing       chan struct{}
\ttlsConfig     *tls.Config
\thelloHostname string
}

type client struct {
\t*smtp.Client
\tfailCount int
}

func NewPool(address string, count int, auth smtp.Auth, opt_tlsConfig ...*tls.Config) (pool *Pool, err error) {
\tpool = &Pool{
\t\taddr:    address,
\t\tauth:    auth,
\t\tmax:     count,
\t\tclients: make(chan *client, count),
\trebuild: make(chan struct{}),
\t\tclosing: make(chan struct{}),
\t\tmut:     &sync.Mutex{},
\t}

\tif len(opt_tlsConfig) == 1 {
\t\tpool.tlsConfig = opt_tlsConfig[0]
\t} else if host, _, e := net.SplitHostPort(address); e != nil {
\t\treturn nil, e
\t} else {
\t\tpool.tlsConfig = &tls.Config{ServerName: host}
\t}

\treturn
}

func (p *Pool) SetHelloHostname(h string) {
\tp.helloHostname = h
}
""",
        "function": "connection_pool_smtp",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "pool.go",
    },
    # ── 11. Pool Send and connection lifecycle management ─────────────
    {
        "normalized_code": """\
import (
\t"errors"
\t"net/mail"
\t"time"
)

var (
\tErrClosed  = errors.New("pool closed")
\tErrTimeout = errors.New("timed out")
)

func (p *Pool) Send(e *Email, timeout time.Duration) (err error) {
\tstart := time.Now()
\tc := p.get(timeout)
\tif c == nil {
\t\treturn p.failedToGet(start)
\t}

\tdefer func() {
\t\tp.maybeReplace(err, c)
\t}()

\trecipients, err := addressLists(e.To, e.Cc, e.Bcc)
\tif err != nil {
\t\treturn
\t}

\tmsg, err := e.Bytes()
\tif err != nil {
\t\treturn
\t}

\tfrom, err := emailOnly(e.From)
\tif err != nil {
\t\treturn
\t}

\tif err = c.Mail(from); err != nil {
\t\treturn
\t}

\tfor _, recip := range recipients {
\t\tif err = c.Rcpt(recip); err != nil {
\t\t\treturn
\t\t}
\t}

\tw, err := c.Data()
\tif err != nil {
\t\treturn
\t}

\tif _, err = w.Write(msg); err != nil {
\t\treturn
\t}

\terr = w.Close()
\treturn
}

func (p *Pool) Close() {
\tclose(p.closing)

\tfor p.created > 0 {
\t\tc := <-p.clients
\t\tc.Quit()
\t\tp.dec()
\t}
}

func emailOnly(full string) (string, error) {
\taddr, err := mail.ParseAddress(full)
\tif err != nil {
\t\treturn "", err
\t}
\treturn addr.Address, nil
}

func addressLists(lists ...[]string) ([]string, error) {
\tlength := 0
\tfor _, lst := range lists {
\t\tlength += len(lst)
\t}
\tcombined := make([]string, 0, length)

\tfor _, lst := range lists {
\t\tfor _, full := range lst {
\t\t\taddr, err := emailOnly(full)
\t\t\tif err != nil {
\t\t\t\treturn nil, err
\t\t\t}
\t\t\tcombined = append(combined, addr)
\t\t}
\t}

\treturn combined, nil
}
""",
        "function": "pool_send_and_lifecycle",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "pool.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "create Email struct from scratch",
    "attach file to email with MIME type",
    "send email via SMTP with authentication",
    "send email with TLS STARTTLS",
    "parse email from RFC 5322 io.Reader",
    "MIME multipart recursive parsing",
    "connection pool bulk email sending",
    "Email to bytes MIME rendering multipart",
    "TLS explicit dial before SMTP",
    "address list parsing and merging",
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
