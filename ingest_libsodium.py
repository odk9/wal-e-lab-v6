"""
ingest_libsodium.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de jedisct1/libsodium dans la KB Qdrant V6.

Focus : CORE patterns cryptographie (secretbox, box, signing, hashing, KDF,
stream encryption, AEAD, random bytes, sealed box, authentication).

Usage:
    .venv/bin/python3 ingest_libsodium.py
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
REPO_URL = "https://github.com/jedisct1/libsodium.git"
REPO_NAME = "jedisct1/libsodium"
REPO_LOCAL = "/tmp/libsodium"
LANGUAGE = "cpp"
FRAMEWORK = "generic"
STACK = "cpp+libsodium+crypto+security"
CHARTE_VERSION = "1.0"
TAG = "jedisct1/libsodium"
SOURCE_REPO = "https://github.com/jedisct1/libsodium"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Libsodium = cryptographic library for encryption, hashing, signing.
# Patterns CORE : secretbox, box, signing, hashing, KDF, stream encryption, AEAD,
# sealed box, random bytes, authentication.
# U-5 : Keep crypto terms (key, cipher, hash, nonce, signature, client, server).

PATTERNS: list[dict] = [
    # ── 1. Secretbox Encrypt/Decrypt (symmetric encryption) ─────────────────
    {
        "normalized_code": """\
#include <sodium.h>
#include <stdio.h>
#include <string.h>

int xxx_encrypt_decrypt(void) {
    unsigned char key[crypto_secretbox_KEYBYTES];
    unsigned char nonce[crypto_secretbox_NONCEBYTES];
    unsigned char plaintext[256];
    unsigned char ciphertext[256 + crypto_secretbox_MACBYTES];

    randombytes(key, sizeof(key));
    randombytes(nonce, sizeof(nonce));
    strcpy((char*)plaintext, "secret payload");

    if (crypto_secretbox_easy(ciphertext, plaintext,
                              strlen((char*)plaintext), nonce, key) != 0) {
        return 1;
    }

    unsigned char decrypted[256];
    if (crypto_secretbox_open_easy(decrypted, ciphertext,
                                   strlen((char*)plaintext) + crypto_secretbox_MACBYTES,
                                   nonce, key) != 0) {
        return 1;
    }

    return 0;
}
""",
        "function": "secretbox_encrypt_decrypt",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/libsodium/crypto_secretbox/xsalsa20poly1305/secretbox.c",
    },
    # ── 2. Box Keypair Generation and Key Exchange ──────────────────────────
    {
        "normalized_code": """\
#include <sodium.h>

int xxx_keypair_exchange(void) {
    unsigned char public_key_a[crypto_box_PUBLICKEYBYTES];
    unsigned char secret_key_a[crypto_box_SECRETKEYBYTES];
    unsigned char public_key_b[crypto_box_PUBLICKEYBYTES];
    unsigned char secret_key_b[crypto_box_SECRETKEYBYTES];

    if (crypto_box_keypair(public_key_a, secret_key_a) != 0) {
        return 1;
    }
    if (crypto_box_keypair(public_key_b, secret_key_b) != 0) {
        return 1;
    }

    unsigned char nonce[crypto_box_NONCEBYTES];
    unsigned char plaintext[32];
    unsigned char ciphertext[32 + crypto_box_MACBYTES];

    randombytes(nonce, sizeof(nonce));

    if (crypto_box_easy(ciphertext, plaintext, sizeof(plaintext),
                        nonce, public_key_b, secret_key_a) != 0) {
        return 1;
    }

    unsigned char decrypted[32];
    if (crypto_box_open_easy(decrypted, ciphertext, sizeof(ciphertext),
                             nonce, public_key_a, secret_key_b) != 0) {
        return 1;
    }

    return 0;
}
""",
        "function": "box_keypair_exchange",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/libsodium/crypto_box/curve25519xsalsa20poly1305/box.c",
    },
    # ── 3. Sign Message and Verify ──────────────────────────────────────────
    {
        "normalized_code": """\
#include <sodium.h>

int xxx_payload_verify(void) {
    unsigned char public_key[crypto_sign_PUBLICKEYBYTES];
    unsigned char secret_key[crypto_sign_SECRETKEYBYTES];
    unsigned char payload[256];
    unsigned char signature[crypto_sign_BYTES];
    unsigned long long signature_len;

    if (crypto_sign_keypair(public_key, secret_key) != 0) {
        return 1;
    }

    strcpy((char*)payload, "payload to sign");
    int payload_len = strlen((char*)payload);

    if (crypto_sign_detached(signature, &signature_len, payload,
                            payload_len, secret_key) != 0) {
        return 1;
    }

    if (crypto_sign_verify_detached(signature, payload,
                                    payload_len, public_key) != 0) {
        return 1;
    }

    return 0;
}
""",
        "function": "sign_payload_verify",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/libsodium/crypto_sign/ed25519/sign.c",
    },
    # ── 4. Generic Hash with BLAKE2b ───────────────────────────────────────
    {
        "normalized_code": """\
#include <sodium.h>

int xxx_hash_blake2b(void) {
    unsigned char payload[256];
    unsigned char hash[crypto_generichash_BYTES];

    strcpy((char*)payload, "payload to hash");
    int payload_len = strlen((char*)payload);

    if (crypto_generichash(hash, sizeof(hash),
                          payload, payload_len, NULL, 0) != 0) {
        return 1;
    }

    crypto_generichash_state state;
    if (crypto_generichash_init(&state, NULL, 0, crypto_generichash_BYTES) != 0) {
        return 1;
    }

    if (crypto_generichash_update(&state, payload, payload_len) != 0) {
        return 1;
    }

    unsigned char incremental_hash[crypto_generichash_BYTES];
    if (crypto_generichash_final(&state, incremental_hash) != 0) {
        return 1;
    }

    return 0;
}
""",
        "function": "generic_hash_blake2b",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/libsodium/crypto_generichash/blake2b/generichash_blake2b.c",
    },
    # ── 5. Password Hashing with Argon2 ────────────────────────────────────
    {
        "normalized_code": """\
#include <sodium.h>

int xxx_hash_argon2(void) {
    unsigned char hash[crypto_pwhash_STRBYTES];
    const char *password = "user_password";
    unsigned char salt[crypto_pwhash_SALTBYTES];

    randombytes(salt, sizeof(salt));

    if (crypto_pwhash_str(hash, password, strlen(password),
                         crypto_pwhash_OPSLIMIT_INTERACTIVE,
                         crypto_pwhash_MEMLIMIT_INTERACTIVE) != 0) {
        return 1;
    }

    if (crypto_pwhash_str_verify(hash, password, strlen(password)) != 0) {
        return 1;
    }

    unsigned char key[32];
    if (crypto_pwhash(key, sizeof(key), password, strlen(password),
                      salt, crypto_pwhash_OPSLIMIT_SENSITIVE,
                      crypto_pwhash_MEMLIMIT_SENSITIVE,
                      crypto_pwhash_ALG_DEFAULT) != 0) {
        return 1;
    }

    return 0;
}
""",
        "function": "password_hash_argon2",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/libsodium/crypto_pwhash/argon2/pwhash_argon2.c",
    },
    # ── 6. Key Derivation with KDF ──────────────────────────────────────────
    {
        "normalized_code": """\
#include <sodium.h>

int xxx_derivation_kdf(void) {
    unsigned char master_key[crypto_kdf_KEYBYTES];
    unsigned char subkey[32];
    const char *context = "example";
    uint64_t subkey_id = 1;

    randombytes(master_key, sizeof(master_key));

    if (crypto_kdf_derive_from_key(subkey, sizeof(subkey), subkey_id,
                                   context, master_key) != 0) {
        return 1;
    }

    unsigned char subkey2[32];
    subkey_id = 2;
    if (crypto_kdf_derive_from_key(subkey2, sizeof(subkey2), subkey_id,
                                   context, master_key) != 0) {
        return 1;
    }

    return 0;
}
""",
        "function": "key_derivation_kdf",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/libsodium/crypto_kdf/blake2b/kdf.c",
    },
    # ── 7. Stream Encryption with XChaCha20 ─────────────────────────────────
    {
        "normalized_code": """\
#include <sodium.h>

int xxx_encryption_xchacha20(void) {
    unsigned char key[crypto_stream_xchacha20_KEYBYTES];
    unsigned char nonce[crypto_stream_xchacha20_NONCEBYTES];
    unsigned char plaintext[256];
    unsigned char ciphertext[256];

    randombytes(key, sizeof(key));
    randombytes(nonce, sizeof(nonce));
    strcpy((char*)plaintext, "plaintext to encrypt");

    if (crypto_stream_xchacha20_xor(ciphertext, plaintext,
                                    strlen((char*)plaintext),
                                    nonce, key) != 0) {
        return 1;
    }

    unsigned char decrypted[256];
    if (crypto_stream_xchacha20_xor(decrypted, ciphertext,
                                    strlen((char*)plaintext),
                                    nonce, key) != 0) {
        return 1;
    }

    return 0;
}
""",
        "function": "stream_encryption_xchacha20",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/libsodium/crypto_stream/xchacha20/stream_xchacha20.c",
    },
    # ── 8. AEAD Encrypt/Decrypt (authenticated encryption) ───────────────────
    {
        "normalized_code": """\
#include <sodium.h>

int xxx_aead_encrypt_decrypt(void) {
    unsigned char key[crypto_aead_xchacha20poly1305_KEYBYTES];
    unsigned char nonce[crypto_aead_xchacha20poly1305_NPUBBYTES];
    unsigned char plaintext[256];
    unsigned char ciphertext[256 + crypto_aead_xchacha20poly1305_ABYTES];
    unsigned long long ciphertext_len;

    randombytes(key, sizeof(key));
    randombytes(nonce, sizeof(nonce));
    strcpy((char*)plaintext, "sensitive data");

    if (crypto_aead_xchacha20poly1305_ietf_encrypt(
        ciphertext, &ciphertext_len, plaintext,
        strlen((char*)plaintext), NULL, 0, NULL, nonce, key) != 0) {
        return 1;
    }

    unsigned char decrypted[256];
    unsigned long long decrypted_len;
    if (crypto_aead_xchacha20poly1305_ietf_decrypt(
        decrypted, &decrypted_len, NULL, ciphertext, ciphertext_len,
        NULL, 0, nonce, key) != 0) {
        return 1;
    }

    return 0;
}
""",
        "function": "aead_encrypt_decrypt",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/libsodium/crypto_aead/xchacha20poly1305/aead.c",
    },
    # ── 9. Secret Stream Push/Pull (streaming AEAD) ──────────────────────────
    {
        "normalized_code": """\
#include <sodium.h>

int xxx_stream_push_pull(void) {
    unsigned char key[crypto_secretstream_xchacha20poly1305_KEYBYTES];
    unsigned char header[crypto_secretstream_xchacha20poly1305_HEADERBYTES];
    unsigned char plaintext[256];
    unsigned char ciphertext[256 + crypto_secretstream_xchacha20poly1305_ABYTES];
    unsigned long long ciphertext_len;

    randombytes(key, sizeof(key));

    crypto_secretstream_xchacha20poly1305_state state;
    if (crypto_secretstream_xchacha20poly1305_init_push(&state, header, key) != 0) {
        return 1;
    }

    strcpy((char*)plaintext, "chunk 1");
    if (crypto_secretstream_xchacha20poly1305_push(
        &state, ciphertext, &ciphertext_len, plaintext,
        strlen((char*)plaintext), NULL, 0,
        crypto_secretstream_xchacha20poly1305_TAG_MESSAGE) != 0) {
        return 1;
    }

    crypto_secretstream_xchacha20poly1305_state state_pull;
    if (crypto_secretstream_xchacha20poly1305_init_pull(&state_pull, header, key) != 0) {
        return 1;
    }

    unsigned char decrypted[256];
    unsigned long long decrypted_len;
    unsigned char marker;
    if (crypto_secretstream_xchacha20poly1305_pull(
        &state_pull, decrypted, &decrypted_len, &marker,
        ciphertext, ciphertext_len, NULL, 0) != 0) {
        return 1;
    }

    return 0;
}
""",
        "function": "secret_stream_push_pull",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/libsodium/crypto_secretstream/xchacha20poly1305/secretstream.c",
    },
    # ── 10. Random Bytes Generation ──────────────────────────────────────────
    {
        "normalized_code": """\
#include <sodium.h>

int xxx_randombytes_generation(void) {
    unsigned char buffer[32];
    unsigned char iv[16];
    unsigned char salt[16];

    randombytes(buffer, sizeof(buffer));

    randombytes_buf(iv, sizeof(iv));

    randombytes_uniform(256);

    uint32_t random_u32 = randombytes_random();

    return 0;
}
""",
        "function": "randombytes_generation",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/libsodium/randombytes/randombytes.c",
    },
    # ── 11. Sealed Box (Anonymous Encryption) ────────────────────────────────
    {
        "normalized_code": """\
#include <sodium.h>

int xxx_box_anonymous(void) {
    unsigned char public_key[crypto_box_PUBLICKEYBYTES];
    unsigned char secret_key[crypto_box_SECRETKEYBYTES];
    unsigned char plaintext[256];
    unsigned char ciphertext[256 + crypto_box_SEALBYTES];

    if (crypto_box_keypair(public_key, secret_key) != 0) {
        return 1;
    }

    strcpy((char*)plaintext, "anonymous payload");

    if (crypto_box_seal(ciphertext, plaintext,
                        strlen((char*)plaintext), public_key) != 0) {
        return 1;
    }

    unsigned char decrypted[256];
    if (crypto_box_seal_open(decrypted, ciphertext,
                             strlen((char*)plaintext) + crypto_box_SEALBYTES,
                             public_key, secret_key) != 0) {
        return 1;
    }

    return 0;
}
""",
        "function": "sealed_box_anonymous",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/libsodium/crypto_box/curve25519xsalsa20poly1305/box_seal.c",
    },
    # ── 12. Authentication with HMAC-SHA256 ──────────────────────────────────
    {
        "normalized_code": """\
#include <sodium.h>

int xxx_hmac_sha256(void) {
    unsigned char key[crypto_auth_hmacsha256_KEYBYTES];
    unsigned char payload[256];
    unsigned char hash[crypto_auth_hmacsha256_BYTES];

    randombytes(key, sizeof(key));
    strcpy((char*)payload, "payload to authenticate");

    if (crypto_auth_hmacsha256(hash, payload,
                              strlen((char*)payload), key) != 0) {
        return 1;
    }

    if (crypto_auth_hmacsha256_verify(hash, payload,
                                      strlen((char*)payload), key) != 0) {
        return 1;
    }

    crypto_auth_hmacsha256_state state;
    if (crypto_auth_hmacsha256_init(&state, key) != 0) {
        return 1;
    }

    if (crypto_auth_hmacsha256_update(&state, payload,
                                      strlen((char*)payload)) != 0) {
        return 1;
    }

    unsigned char incremental_hash[crypto_auth_hmacsha256_BYTES];
    if (crypto_auth_hmacsha256_final(&state, incremental_hash) != 0) {
        return 1;
    }

    return 0;
}
""",
        "function": "auth_hmac_sha256",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/libsodium/crypto_auth/hmacsha256/auth_hmacsha256.c",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "secretbox symmetric encryption decrypt nonce key",
    "box curve25519 keypair exchange shared secret",
    "sign verify ed25519 signature detached public key",
    "generic hash blake2b incremental hashing",
    "password hash argon2 key derivation interactive",
    "KDF key derivation subkey context master",
    "stream encryption XChaCha20 stream cipher nonce",
    "AEAD authenticated encryption XChaCha20Poly1305",
    "secret stream push pull chunked authenticated",
    "random bytes uniform buffer generation",
    "sealed box anonymous encryption public key",
    "HMAC SHA256 authentication verify incremental",
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
