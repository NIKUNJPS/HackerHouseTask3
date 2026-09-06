"""Offline smoke tests: fingerprint integrity + on-chain anchor/verify.

These need neither the face models nor the network — only solc (auto-installed)
and the in-process EVM. Run with:  pytest -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from facechain.fingerprint import build_record, compute_fingerprint
from facechain.blockchain import FaceRegistry, connect_chain


SAMPLE_POST = {
    "provider": "local", "platform": "github",
    "url": "https://github.com/example/post", "image_sha256": "ab" * 32,
    "match_score": 0.7437, "face_verified": True,
}


def _make_record():
    return build_record(
        query_image_sha256="11" * 32,
        face_embedding_sha256="22" * 32,
        face_embedding_b64="AAAA",
        post=SAMPLE_POST,
    )


def test_fingerprint_is_deterministic():
    payload = _make_record()["fingerprint_payload"]
    assert compute_fingerprint(payload) == compute_fingerprint(payload)
    assert compute_fingerprint(payload).startswith("0x")
    assert len(compute_fingerprint(payload)) == 66  # 0x + 32 bytes hex


def test_tampering_changes_fingerprint():
    rec = _make_record()
    payload = dict(rec["fingerprint_payload"])
    tampered = {**payload, "match": {**payload["match"], "url": "https://evil/post"}}
    assert compute_fingerprint(tampered) != rec["fingerprint"]


def test_anchor_and_verify_on_chain():
    rec = _make_record()
    ctx = connect_chain("memory")
    reg = FaceRegistry(ctx)
    reg.deploy()

    receipt = reg.anchor(rec["fingerprint"], SAMPLE_POST["url"])
    assert receipt["already_anchored"] is False
    assert reg.count() == 1

    on = reg.read(rec["fingerprint"])
    assert on["exists"] is True
    assert on["uri"] == SAMPLE_POST["url"]
    assert on["timestamp"] > 0

    # re-anchoring the same fingerprint is idempotent (contract reverts on dup)
    again = reg.anchor(rec["fingerprint"], SAMPLE_POST["url"])
    assert again["already_anchored"] is True
    assert reg.count() == 1


def test_unknown_fingerprint_absent():
    ctx = connect_chain("memory")
    reg = FaceRegistry(ctx)
    reg.deploy()
    missing = "0x" + "cd" * 32
    assert reg.read(missing)["exists"] is False
