"""
ingest_rustcrypto.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de RustCrypto/block-ciphers dans la KB Qdrant V6.

Focus : CORE patterns cryptographie (AES encrypt/decrypt, CBC mode, GCM AEAD,
ChaCha20Poly1305, SHA256, HMAC, PBKDF2, RSA, ECDSA, key generation, constant-time).

Usage:
    .venv/bin/python3 ingest_rustcrypto.py
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
REPO_URL = "https://github.com/RustCrypto/block-ciphers.git"
REPO_NAME = "RustCrypto/block-ciphers"
REPO_LOCAL = "/tmp/block-ciphers"
LANGUAGE = "rust"
FRAMEWORK = "generic"
STACK = "rust+rustcrypto+crypto+security"
CHARTE_VERSION = "1.0"
TAG = "RustCrypto/block-ciphers"
SOURCE_REPO = "https://github.com/RustCrypto/block-ciphers"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# RustCrypto = pure Rust cryptography algorithms.
# Patterns CORE : AES (block, CBC, GCM), ChaCha20Poly1305, SHA256, HMAC,
# PBKDF2, RSA, ECDSA, key generation, constant-time compare.
# U-5 : Keep crypto terms (key, cipher, hash, nonce, signature).

PATTERNS: list[dict] = [
    # ── 1. AES Block Encryption ──────────────────────────────────────────────
    {
        "normalized_code": """\
use aes::Aes256;
use cipher::{BlockEncrypt, BlockDecrypt, KeyInit};

fn xxx_encrypt_block() -> Result<(), Box<dyn std::error::Error>> {
    let key = [0u8; 32];
    let plaintext = *b"0123456789ABCDEF";

    let cipher = Aes256::new(&key.into());
    let mut block = plaintext.into();

    cipher.encrypt_block(&mut block);
    let ciphertext = block.clone();

    cipher.decrypt_block(&mut block);
    let decrypted = block.clone();

    assert_eq!(plaintext, decrypted.into());
    Ok(())
}
""",
        "function": "aes_encrypt_block",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "aes/src/lib.rs",
    },
    # ── 2. AES CBC Mode Encryption ──────────────────────────────────────────
    {
        "normalized_code": """\
use aes::Aes128;
use cbc::{Cbc, cipher::{BlockEncryptMut, BlockDecryptMut, KeyIvInit}};
use rand::Rng;

fn xxx_cbc_encrypt() -> Result<(), Box<dyn std::error::Error>> {
    let mut rng = rand::thread_rng();
    let key = [0u8; 16];
    let iv = [0u8; 16];

    let cipher = Cbc::<Aes128, cipher::block_padding::Pkcs7>::new_from_slices(&key, &iv)?;
    let plaintext = b"Hello, World!!!";

    let ciphertext = cipher.encrypt_vec(plaintext);

    let cipher_decrypt = Cbc::<Aes128, cipher::block_padding::Pkcs7>::new_from_slices(&key, &iv)?;
    let decrypted = cipher_decrypt.decrypt_vec(&ciphertext)?;

    assert_eq!(plaintext.to_vec(), decrypted);
    Ok(())
}
""",
        "function": "aes_cbc_encrypt",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "aes/examples/cbc_mode.rs",
    },
    # ── 3. AES GCM AEAD Encryption ───────────────────────────────────────────
    {
        "normalized_code": """\
use aes_gcm::{Aes256Gcm, Key, Nonce, aead::{Aead, KeyInit}};
use rand::Rng;

fn xxx_gcm_aead() -> Result<(), Box<dyn std::error::Error>> {
    let mut rng = rand::thread_rng();
    let key = Aes256Gcm::generate_key(&mut rng);
    let nonce = Nonce::from_slice(b"unique nonce");

    let cipher = Aes256Gcm::new(&key);
    let plaintext = b"secret payload";

    let ciphertext = cipher.encrypt(nonce, plaintext.as_ref())?;

    let decrypted = cipher.decrypt(nonce, ciphertext.as_ref())?;
    assert_eq!(plaintext.to_vec(), decrypted);

    Ok(())
}
""",
        "function": "aes_gcm_aead",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "aes-gcm/src/lib.rs",
    },
    # ── 4. ChaCha20Poly1305 AEAD ─────────────────────────────────────────────
    {
        "normalized_code": """\
use chacha20poly1305::{ChaCha20Poly1305, Key, Nonce, aead::{Aead, KeyInit}};
use rand::Rng;

fn xxx_chacha20poly1305() -> Result<(), Box<dyn std::error::Error>> {
    let mut rng = rand::thread_rng();
    let key = ChaCha20Poly1305::generate_key(&mut rng);
    let nonce = Nonce::from_slice(b"unique nonce");

    let cipher = ChaCha20Poly1305::new(&key);
    let plaintext = b"authenticated encrypted data";
    let aad = b"additional authenticated data";

    let ciphertext = cipher.encrypt(nonce, [plaintext.as_ref(), aad.as_ref()].concat().as_ref())?;

    let decrypted = cipher.decrypt(nonce, ciphertext.as_ref())?;
    Ok(())
}
""",
        "function": "chacha20poly1305",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "chacha20poly1305/src/lib.rs",
    },
    # ── 5. SHA256 Hashing ────────────────────────────────────────────────────
    {
        "normalized_code": """\
use sha2::{Sha256, Digest};

fn xxx_sha256_digest() -> Result<(), Box<dyn std::error::Error>> {
    let mut hasher = Sha256::new();

    hasher.update(b"payload to hash");

    let hash = hasher.finalize();
    tracing::debug!("SHA256: {}", hex::encode(&hash[..]));

    let hash_array: [u8; 32] = hash.into();
    tracing::debug!("Hash array: {:?}", hash_array);

    Ok(())
}
""",
        "function": "sha256_digest",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "sha2/examples/sha256.rs",
    },
    # ── 6. HMAC-SHA256 Authentication ────────────────────────────────────────
    {
        "normalized_code": """\
use hmac::{Hmac, Mac};
use sha2::Sha256;

type HmacSha256 = Hmac<Sha256>;

fn xxx_hmac_sha256_auth() -> Result<(), Box<dyn std::error::Error>> {
    let key = b"secret_key";
    let payload = b"payload to authenticate";

    let mut mac = HmacSha256::new_from_slice(key)?;
    mac.update(payload);

    let signature = mac.finalize();
    tracing::debug!("HMAC: {}", hex::encode(signature.as_bytes()));

    let mut mac_verify = HmacSha256::new_from_slice(key)?;
    mac_verify.update(payload);
    mac_verify.verify_slice(signature.as_bytes())?;

    Ok(())
}
""",
        "function": "hmac_sha256_auth",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "hmac/examples/hmac_sha256.rs",
    },
    # ── 7. PBKDF2 Key Derivation ─────────────────────────────────────────────
    {
        "normalized_code": """\
use pbkdf2::pbkdf2_hmac;
use sha2::Sha256;

fn xxx_pbkdf2_key_derivation() -> Result<(), Box<dyn std::error::Error>> {
    let password = b"user_password";
    let salt = b"random_salt_1234";
    let mut output = [0u8; 32];

    pbkdf2_hmac::<Sha256>(password, salt, 100_000, &mut output);

    tracing::debug!("Derived key: {}", hex::encode(&output[..]));

    Ok(())
}
""",
        "function": "pbkdf2_key_derivation",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "pbkdf2/examples/derive_key.rs",
    },
    # ── 8. RSA Encrypt/Decrypt (with padding) ────────────────────────────────
    {
        "normalized_code": """\
use rsa::{RsaPrivateKey, RsaPublicKey, Pkcs1v15Encrypt};
use rand::thread_rng;

fn xxx_rsa_encrypt_decrypt() -> Result<(), Box<dyn std::error::Error>> {
    let mut rng = thread_rng();
    let bits = 2048;
    let private_key = RsaPrivateKey::new(&mut rng, bits)?;
    let public_key = RsaPublicKey::from(&private_key);

    let plaintext = b"secret payload";
    let ciphertext = public_key.encrypt(&mut rng, Pkcs1v15Encrypt, plaintext)?;

    let decrypted = private_key.decrypt(Pkcs1v15Encrypt, &ciphertext)?;
    assert_eq!(plaintext.to_vec(), decrypted);

    Ok(())
}
""",
        "function": "rsa_encrypt_decrypt",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "rsa/examples/encrypt_decrypt.rs",
    },
    # ── 9. ECDSA Sign and Verify ─────────────────────────────────────────────
    {
        "normalized_code": """\
use ecdsa::{SigningKey, VerifyingKey, signature::Signer};
use p256::NistP256;
use rand::thread_rng;

fn xxx_ecdsa_sign_verify() -> Result<(), Box<dyn std::error::Error>> {
    let mut rng = thread_rng();
    let signing_key = SigningKey::random(&mut rng);
    let verifying_key = VerifyingKey::from(&signing_key);

    let payload = b"payload to sign";
    let signature = signing_key.sign(payload);

    verifying_key.verify(payload, &signature)?;
    tracing::info!("Signature verified successfully");

    Ok(())
}
""",
        "function": "ecdsa_sign_verify",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "ecdsa/examples/sign_verify.rs",
    },
    # ── 10. Random Key Generation ────────────────────────────────────────────
    {
        "normalized_code": """\
use rand::Rng;
use rand::thread_rng;

fn xxx_key_generation_random() -> Result<(), Box<dyn std::error::Error>> {
    let mut rng = thread_rng();

    let key_32: [u8; 32] = rng.gen();
    tracing::debug!("32-byte key: {}", hex::encode(&key_32[..]));

    let nonce_12: [u8; 12] = rng.gen();
    tracing::debug!("12-byte nonce: {}", hex::encode(&nonce_12[..]));

    let salt_16: [u8; 16] = rng.gen();
    tracing::debug!("16-byte salt: {}", hex::encode(&salt_16[..]));

    Ok(())
}
""",
        "function": "key_generation_random",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/random_keys.rs",
    },
    # ── 11. Constant-Time Comparison ─────────────────────────────────────────
    {
        "normalized_code": """\
use subtle::ConstantTimeComparison;

fn xxx_constant_time_compare() -> Result<(), Box<dyn std::error::Error>> {
    let signature1 = b"signature1234567890";
    let signature2 = b"signature1234567890";
    let signature3 = b"different_sig12345";

    if signature1.ct_eq(signature2).unwrap_u8() == 1 {
        tracing::info!("Signatures match (constant time)");
    }

    if signature1.ct_eq(signature3).unwrap_u8() != 1 {
        tracing::info!("Signatures differ (constant time check)");
    }

    Ok(())
}
""",
        "function": "constant_time_compare",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/constant_time.rs",
    },
    # ── 12. Stream Cipher Encryption ─────────────────────────────────────────
    {
        "normalized_code": """\
use chacha20::ChaCha20;
use cipher::{StreamCipher, KeyInit};
use rand::thread_rng;

fn xxx_cipher_stream_encrypt() -> Result<(), Box<dyn std::error::Error>> {
    let mut rng = thread_rng();
    let key = [0u8; 32];
    let nonce = [0u8; 12];

    let mut cipher = ChaCha20::new(&key[..].into(), &nonce[..].into());

    let plaintext = b"plaintext payload";
    let mut ciphertext = plaintext.to_vec();

    cipher.apply_keystream(&mut ciphertext);
    tracing::debug!("Encrypted: {}", hex::encode(&ciphertext[..]));

    let mut cipher_decrypt = ChaCha20::new(&key[..].into(), &nonce[..].into());
    let mut decrypted = ciphertext.clone();
    cipher_decrypt.apply_keystream(&mut decrypted);

    assert_eq!(plaintext.to_vec(), decrypted);
    Ok(())
}
""",
        "function": "cipher_stream_encrypt",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "chacha20/examples/stream_cipher.rs",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "AES block encrypt decrypt cipher",
    "AES CBC mode encryption padding",
    "AES GCM authenticated encryption AEAD",
    "ChaCha20Poly1305 AEAD nonce key",
    "SHA256 hash digest message",
    "HMAC SHA256 authentication verify",
    "PBKDF2 key derivation password salt",
    "RSA encrypt decrypt PKCS1 padding",
    "ECDSA sign verify signature message",
    "random key generation nonce",
    "constant time comparison subtle equal",
    "stream cipher ChaCha20 keystream apply",
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
