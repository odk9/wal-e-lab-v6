"""
ingest_cryptography.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de pyca/cryptography dans la KB Qdrant V6.

Focus : Patterns Core pour cryptographie en Python — Fernet encryption,
AES-GCM, RSA keys/signatures, X.509 certificates, password hashing,
HMAC authentication, ECDSA signatures, TLS/CA, key serialization, CSR.

Usage:
    .venv/bin/python3 ingest_cryptography.py
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
REPO_URL = "https://github.com/pyca/cryptography.git"
REPO_NAME = "pyca/cryptography"
REPO_LOCAL = "/tmp/cryptography"
LANGUAGE = "python"
FRAMEWORK = "generic"
STACK = "python+cryptography+security"
CHARTE_VERSION = "1.0"
TAG = "pyca/cryptography"
SOURCE_REPO = "https://github.com/pyca/cryptography"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Cryptography = Security library pour Python.
# Patterns CORE : Fernet encryption, AES-GCM, RSA key generation and signing,
# X.509 certificates, password hashing, HMAC, ECDSA, TLS/CA, serialization.
# U-5 : `certificate`, `key`, `cipher`, `hash`, `token`, `password` sont OK.

PATTERNS: list[dict] = [
    # ── 1. Fernet Encryption and Decryption ────────────────────────────────────
    {
        "normalized_code": """\
from cryptography.fernet import Fernet

class XxxCipher:
    \"\"\"Symmetric encryption using Fernet (AES in CBC mode + HMAC).\"\"\"

    def __init__(self, key: bytes | None = None):
        if key is None:
            key = Fernet.generate_key()
        self._cipher = Fernet(key)
        self.key = key

    def encrypt(self, plaintext: bytes) -> bytes:
        \"\"\"Encrypt plaintext with Fernet.\"\"\"
        return self._cipher.encrypt(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        \"\"\"Decrypt ciphertext with Fernet.

        Raises InvalidToken if MAC verification fails.
        \"\"\"
        return self._cipher.decrypt(ciphertext)

    def encrypt_text(self, text: str) -> str:
        \"\"\"Encrypt text string and return base64-encoded ciphertext.\"\"\"
        ciphertext = self.encrypt(text.encode("utf-8"))
        return ciphertext.decode("utf-8")

    def decrypt_text(self, ciphertext: str) -> str:
        \"\"\"Decrypt base64-encoded ciphertext and return text.\"\"\"
        plaintext = self.decrypt(ciphertext.encode("utf-8"))
        return plaintext.decode("utf-8")
""",
        "function": "fernet_encrypt_decrypt",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "cryptography/fernet.py",
    },
    # ── 2. AES-GCM Encryption ──────────────────────────────────────────────────
    {
        "normalized_code": """\
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class XxxAESCipher:
    \"\"\"AES-GCM authenticated encryption.\"\"\"

    KEY_SIZE = 32  # 256-bit key
    NONCE_SIZE = 12  # 96-bit nonce

    def __init__(self, key: bytes | None = None):
        if key is None:
            key = os.urandom(self.KEY_SIZE)
        self.key = key

    def encrypt(self, plaintext: bytes, associated_data: bytes | None = None) -> tuple[bytes, bytes]:
        \"\"\"Encrypt plaintext with AES-GCM.

        Returns (nonce, ciphertext). Nonce is randomly generated.
        \"\"\"
        nonce = os.urandom(self.NONCE_SIZE)
        cipher = AESGCM(self.key)
        ciphertext = cipher.encrypt(nonce, plaintext, associated_data)
        return nonce, ciphertext

    def decrypt(self, nonce: bytes, ciphertext: bytes, associated_data: bytes | None = None) -> bytes:
        \"\"\"Decrypt ciphertext with AES-GCM.

        Raises InvalidDigest if authentication digest verification fails.
        \"\"\"
        cipher = AESGCM(self.key)
        return cipher.decrypt(nonce, ciphertext, associated_data)

    def encrypt_with_aad(self, plaintext: bytes, aad: str) -> tuple[bytes, bytes]:
        \"\"\"Encrypt plaintext with additional authenticated data (AAD).\"\"\"
        return self.encrypt(plaintext, aad.encode("utf-8"))
""",
        "function": "aes_gcm_encryption",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "cryptography/hazmat/primitives/ciphers/aead.py",
    },
    # ── 3. RSA Key Generation ──────────────────────────────────────────────────
    {
        "normalized_code": """\
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

class XxxRSAKeyPair:
    \"\"\"RSA key pair generation and serialization.\"\"\"

    def __init__(self, key_size: int = 2048):
        self.key_size = key_size
        self.private_key = self._generate_private_key()
        self.public_key = self.private_key.public_key()

    def _generate_private_key(self):
        \"\"\"Generate RSA private key.\"\"\"
        return rsa.generate_private_key(
            public_exponent=65537,
            key_size=self.key_size,
        )

    def serialize_private_key_pem(self, password: bytes | None = None) -> bytes:
        \"\"\"Serialize private key to PEM format (optionally encrypted).\"\"\"
        if password:
            encryption = serialization.BestAvailableEncryption(password)
        else:
            encryption = serialization.NoEncryption()

        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=encryption,
        )

    def serialize_public_key_pem(self) -> bytes:
        \"\"\"Serialize public key to PEM format.\"\"\"
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    @classmethod
    def load_private_key_pem(cls, key_data: bytes, password: bytes | None = None):
        \"\"\"Load RSA private key from PEM.\"\"\"
        private_key = serialization.load_pem_private_key(key_data, password)
        instance = cls.__new__(cls)
        instance.private_key = private_key
        instance.public_key = private_key.public_key()
        return instance
""",
        "function": "rsa_key_generation",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "cryptography/hazmat/primitives/asymmetric/rsa.py",
    },
    # ── 4. RSA Sign and Verify ─────────────────────────────────────────────────
    {
        "normalized_code": """\
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes

class XxxRSASignature:
    \"\"\"RSA signature creation and verification (PKCS1v15 + SHA256).\"\"\"

    def __init__(self, key_pair):
        self.key_pair = key_pair

    def sign(self, data: bytes) -> bytes:
        \"\"\"Sign data with RSA private key.\"\"\"
        return self.key_pair.private_key.sign(
            data,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )

    def verify(self, data: bytes, signature: bytes) -> bool:
        \"\"\"Verify signature with RSA public key.

        Returns True if valid, raises InvalidSignature if invalid.
        \"\"\"
        try:
            self.key_pair.public_key.verify(
                signature,
                data,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return True
        except Exception:
            return False

    def sign_text(self, text: str) -> bytes:
        \"\"\"Sign text string (UTF-8 encoded).\"\"\"
        return self.sign(text.encode("utf-8"))

    def verify_text(self, text: str, signature: bytes) -> bool:
        \"\"\"Verify signature of text string.\"\"\"
        return self.verify(text.encode("utf-8"), signature)
""",
        "function": "rsa_sign_verify",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "cryptography/hazmat/primitives/asymmetric/padding.py",
    },
    # ── 5. X.509 Certificate Generation ────────────────────────────────────────
    {
        "normalized_code": """\
from datetime import datetime, UTC

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

class XxxCertificateBuilder:
    \"\"\"Generate self-signed X.509 certificates.\"\"\"

    def __init__(self):
        self.private_key = rsa.generate_private_key(65537, 2048)

    def build_self_signed_cert(self, common_name: str) -> x509.Certificate:
        \"\"\"Create self-signed certificate.\"\"\"
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "City"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Xxx Org"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(self.private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(UTC))
            .not_valid_after(datetime.now(UTC) + timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName(common_name),
                    x509.DNSName("*." + common_name),
                ]),
                critical=False,
            )
            .sign(self.private_key, hashes.SHA256())
        )

        return cert
""",
        "function": "x509_certificate_generate",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "cryptography/x509/certificate_builder.py",
    },
    # ── 6. X.509 Certificate Parsing ───────────────────────────────────────────
    {
        "normalized_code": """\
from datetime import datetime, UTC

from cryptography import x509
from cryptography.hazmat.primitives import serialization

class XxxCertificateParser:
    \"\"\"Parse and inspect X.509 certificates.\"\"\"

    @staticmethod
    def load_certificate_pem(certificate_data: bytes) -> x509.Certificate:
        \"\"\"Load X.509 certificate from PEM format.\"\"\"
        return x509.load_pem_x509_certificate(certificate_data)

    @staticmethod
    def load_certificate_der(certificate_data: bytes) -> x509.Certificate:
        \"\"\"Load X.509 certificate from DER format.\"\"\"
        return x509.load_der_x509_certificate(certificate_data)

    @staticmethod
    def inspect_certificate(cert: x509.Certificate) -> dict:
        \"\"\"Extract certificate details.\"\"\"
        return {
            "subject": cert.subject.rfc4514_string(),
            "issuer": cert.issuer.rfc4514_string(),
            "serial_number": cert.serial_number,
            "not_valid_before": cert.not_valid_before,
            "not_valid_after": cert.not_valid_after,
            "public_key_type": type(cert.public_key()).__name__,
            "signature_algorithm": cert.signature_algorithm_oid._name,
        }

    @staticmethod
    def is_certificate_valid(cert: x509.Certificate) -> bool:
        \"\"\"Check if certificate is currently valid.\"\"\"
        now = datetime.now(UTC)
        return cert.not_valid_before <= now <= cert.not_valid_after
""",
        "function": "x509_certificate_parse",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "cryptography/x509/loader.py",
    },
    # ── 7. Password Hashing with PBKDF2 ────────────────────────────────────────
    {
        "normalized_code": """\
import os
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
from cryptography.hazmat.primitives import hashes

class XxxPasswordHasher:
    \"\"\"Password hashing using PBKDF2-SHA256.\"\"\"

    ITERATIONS = 480000  # NIST recommendation as of 2023
    SALT_SIZE = 16

    def __init__(self):
        pass

    def hash_password(self, password: str) -> tuple[bytes, bytes]:
        \"\"\"Hash password and return (salt, hash).\"\"\"
        salt = os.urandom(self.SALT_SIZE)
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self.ITERATIONS,
        )
        hash_value = kdf.derive(password.encode("utf-8"))
        return salt, hash_value

    def verify_password(self, password: str, salt: bytes, hash_value: bytes) -> bool:
        \"\"\"Verify password against stored hash.\"\"\"
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self.ITERATIONS,
        )
        try:
            kdf.verify(password.encode("utf-8"), hash_value)
            return True
        except Exception:
            return False

    def hash_password_b64(self, password: str) -> str:
        \"\"\"Hash password and return as 'salt:hash' base64-encoded string.\"\"\"
        import base64
        salt, hash_value = self.hash_password(password)
        return base64.b64encode(salt + hash_value).decode("utf-8")
""",
        "function": "password_hashing_pbkdf2",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "cryptography/hazmat/primitives/kdf/pbkdf2.py",
    },
    # ── 8. HMAC Message Authentication ──────────────────────────────────────────
    {
        "normalized_code": """\
from cryptography.hazmat.primitives import hashes, hmac

class XxxHMACAuthenticator:
    \"\"\"HMAC-SHA256 data authentication.\"\"\"

    def __init__(self, key: bytes):
        self.key = key

    def generate_digest(self, data: bytes) -> bytes:
        \"\"\"Generate HMAC digest for data.\"\"\"
        h = hmac.HMAC(self.key, hashes.SHA256())
        h.update(data)
        return h.finalize()

    def verify_digest(self, data: bytes, digest: bytes) -> bool:
        \"\"\"Verify HMAC digest.

        Returns True if valid, raises InvalidSignature if tampered.
        \"\"\"
        h = hmac.HMAC(self.key, hashes.SHA256())
        h.update(data)
        try:
            h.verify(digest)
            return True
        except Exception:
            return False

    def authenticate_text(self, text: str) -> bytes:
        \"\"\"Generate HMAC digest for text string.\"\"\"
        return self.generate_digest(text.encode("utf-8"))

    def verify_text(self, text: str, digest: bytes) -> bool:
        \"\"\"Verify HMAC digest for text string.\"\"\"
        return self.verify_digest(text.encode("utf-8"), digest)
""",
        "function": "hmac_message_auth",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "cryptography/hazmat/primitives/hmac.py",
    },
    # ── 9. ECDSA Sign and Verify ───────────────────────────────────────────────
    {
        "normalized_code": """\
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes

class XxxECDSASignature:
    \"\"\"ECDSA signature with P-256 curve and SHA256.\"\"\"

    def __init__(self, private_key=None):
        if private_key is None:
            private_key = ec.generate_private_key(ec.SECP256R1())
        self.private_key = private_key
        self.public_key = private_key.public_key()

    @classmethod
    def generate_keypair(cls):
        \"\"\"Generate new ECDSA keypair.\"\"\"
        return cls()

    def sign(self, data: bytes) -> bytes:
        \"\"\"Sign data with ECDSA.\"\"\"
        return self.private_key.sign(data, ec.ECDSA(hashes.SHA256()))

    def verify(self, data: bytes, signature: bytes) -> bool:
        \"\"\"Verify ECDSA signature.

        Returns True if valid, raises InvalidSignature if invalid.
        \"\"\"
        try:
            self.public_key.verify(signature, data, ec.ECDSA(hashes.SHA256()))
            return True
        except Exception:
            return False

    def sign_text(self, text: str) -> bytes:
        \"\"\"Sign text string.\"\"\"
        return self.sign(text.encode("utf-8"))

    def verify_text(self, text: str, signature: bytes) -> bool:
        \"\"\"Verify signature of text string.\"\"\"
        return self.verify(text.encode("utf-8"), signature)
""",
        "function": "ecdsa_sign_verify",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "cryptography/hazmat/primitives/asymmetric/ec.py",
    },
    # ── 10. TLS Certificate Authority ──────────────────────────────────────────
    {
        "normalized_code": """\
from datetime import datetime, timedelta, UTC

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

class XxxTLSCertificateAuthority:
    \"\"\"Self-signed CA for issuing TLS certificates.\"\"\"

    def __init__(self):
        self.private_key = rsa.generate_private_key(65537, 2048)
        self.certificate = self._create_ca_cert()

    def _create_ca_cert(self) -> x509.Certificate:
        \"\"\"Create self-signed CA certificate.\"\"\"
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Xxx CA"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Xxx Certificate Authority"),
        ])

        return (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(self.private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(UTC))
            .not_valid_after(datetime.now(UTC) + timedelta(days=3650))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=None),
                critical=True,
            )
            .sign(self.private_key, hashes.SHA256())
        )

    def issue_certificate(self, csr: x509.CertificateSigningRequest, days: int = 365) -> x509.Certificate:
        \"\"\"Issue TLS certificate from CSR.\"\"\"
        return (
            x509.CertificateBuilder()
            .subject_name(csr.subject)
            .issuer_name(self.certificate.subject)
            .public_key(csr.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(UTC))
            .not_valid_after(datetime.now(UTC) + timedelta(days=days))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .sign(self.private_key, hashes.SHA256())
        )
""",
        "function": "tls_certificate_authority",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "cryptography/x509/certificate_authority.py",
    },
    # ── 11. Key Serialization to PEM ───────────────────────────────────────────
    {
        "normalized_code": """\
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

class XxxKeySerializer:
    \"\"\"Serialize cryptographic keys to standard formats (PEM, DER).\"\"\"

    @staticmethod
    def serialize_private_key_pem(private_key, password: bytes | None = None) -> bytes:
        \"\"\"Serialize private key to PEM (optionally encrypted with password).\"\"\"
        if password:
            encryption = serialization.BestAvailableEncryption(password)
        else:
            encryption = serialization.NoEncryption()

        return private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=encryption,
        )

    @staticmethod
    def serialize_public_key_pem(public_key) -> bytes:
        \"\"\"Serialize public key to PEM.\"\"\"
        return public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    @staticmethod
    def deserialize_private_key_pem(key_data: bytes, password: bytes | None = None):
        \"\"\"Deserialize private key from PEM.\"\"\"
        return serialization.load_pem_private_key(key_data, password)

    @staticmethod
    def deserialize_public_key_pem(key_data: bytes):
        \"\"\"Deserialize public key from PEM.\"\"\"
        return serialization.load_pem_public_key(key_data)
""",
        "function": "key_serialization_pem",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "cryptography/hazmat/primitives/serialization.py",
    },
    # ── 12. Certificate Signing Request ────────────────────────────────────────
    {
        "normalized_code": """\
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

class XxxCertificateSigningRequest:
    \"\"\"Generate X.509 Certificate Signing Requests (CSR).\"\"\"

    def __init__(self):
        self.private_key = rsa.generate_private_key(65537, 2048)

    def build_csr(self, common_name: str, organization: str = "Xxx Org") -> bytes:
        \"\"\"Create CSR in PEM format.\"\"\"
        subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "City"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])

        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(subject)
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName(common_name),
                    x509.DNSName("*." + common_name),
                ]),
                critical=False,
            )
            .sign(self.private_key, hashes.SHA256())
        )

        from cryptography.hazmat.primitives import serialization
        return csr.public_bytes(serialization.Encoding.PEM)

    def serialize_private_key_pem(self, password: bytes | None = None) -> bytes:
        \"\"\"Serialize private key corresponding to CSR.\"\"\"
        from cryptography.hazmat.primitives import serialization
        if password:
            encryption = serialization.BestAvailableEncryption(password)
        else:
            encryption = serialization.NoEncryption()

        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=encryption,
        )
""",
        "function": "certificate_signing_request",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "cryptography/x509/certificate_signing_request.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "Fernet symmetric encryption decryption",
    "AES-GCM authenticated encryption with nonce",
    "RSA key generation private public PEM",
    "RSA sign verify PKCS1v15 SHA256",
    "X.509 self-signed certificate generation",
    "X.509 certificate parsing load inspect",
    "password hashing PBKDF2 SHA256 iterations",
    "HMAC-SHA256 message authentication tag",
    "ECDSA sign verify P-256 secp256r1",
    "TLS certificate authority issuer CSR",
    "key serialization deserialize PEM PKCS8",
    "certificate signing request CSR generation",
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
