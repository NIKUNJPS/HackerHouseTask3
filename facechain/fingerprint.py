"""Canonical record construction + tamper-evident fingerprinting.

The *fingerprint* is ``keccak256`` over a canonical (sorted, compact) JSON of the
essential facts about a match. That 32-byte value is what gets anchored on-chain.
Re-verification recomputes the fingerprint from the saved record and checks it
against the ledger — any edit to the record changes the fingerprint and fails.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from web3 import Web3


def canonical_json(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_payload(*, query_image_sha256: str, face_embedding_sha256: str,
                  post: dict, created_at: str) -> dict:
    """The exact sub-object that is hashed. Deterministic and self-contained."""
    return {
        "schema": "facechain/fingerprint/v1",
        "created_at": created_at,
        "query": {
            "image_sha256": query_image_sha256,
            "face_embedding_sha256": face_embedding_sha256,
        },
        "match": {
            "provider": post.get("provider", ""),
            "platform": post.get("platform", ""),
            "url": post.get("url", ""),
            "image_sha256": post.get("image_sha256", ""),
            "match_score": post.get("match_score", 0.0),
            "face_verified": bool(post.get("face_verified", False)),
        },
    }


def compute_fingerprint(payload: dict) -> str:
    """Return the 0x-prefixed keccak256 hex of the canonical payload."""
    return Web3.keccak(canonical_json(payload)).hex()


def build_record(*, query_image_sha256: str, face_embedding_sha256: str,
                 face_embedding_b64: str, post: dict) -> dict:
    """Assemble the full, human-readable record (payload + extras)."""
    created_at = now_iso()
    payload = build_payload(
        query_image_sha256=query_image_sha256,
        face_embedding_sha256=face_embedding_sha256,
        post=post,
        created_at=created_at,
    )
    fingerprint = compute_fingerprint(payload)
    return {
        "fingerprint": fingerprint,
        "fingerprint_payload": payload,
        "created_at": created_at,
        "query": {
            "image_sha256": query_image_sha256,
            "face_embedding_sha256": face_embedding_sha256,
            "face_embedding_b64": face_embedding_b64,
        },
        "match": dict(post),
        "chain": None,  # filled in after anchoring
    }
