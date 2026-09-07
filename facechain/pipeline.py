"""End-to-end orchestrator: face scan -> social search -> blockchain anchor + verify."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from . import config, log
from .face import FaceRecognizer, NoFaceFound
from .search import base as search_base
from .fingerprint import build_record, compute_fingerprint
from .blockchain import FaceRegistry, connect_chain


def _sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _short(fp: str) -> str:
    return (fp[2:] if fp.startswith("0x") else fp)[:16]


class PipelineError(Exception):
    pass


def run(image_path: str, *, provider: str = "auto", chain: str = None,
        redeploy: bool = False, allow_unverified: bool = False) -> dict:
    """Run the full pipeline and return a result dict."""
    image_path = str(image_path)
    if not Path(image_path).exists():
        raise PipelineError(f"input image not found: {image_path}")
    chain = chain or config.DEFAULT_CHAIN

    log.banner("FaceChain — Face → Social Search → Blockchain",
               "tamper-evident identity verification pipeline")

    # ---- STEP 1: face detection + encoding --------------------------------
    log.step("Face scan — detect & encode")
    recognizer = FaceRecognizer()
    img_sha = _sha256_file(image_path)
    log.kv("input image", image_path)
    log.kv("image sha256", img_sha)
    with log.timed("face detection"):
        faces = recognizer.detect_faces(image_path)
    if not faces:
        raise PipelineError("no face detected in the input image")
    face = faces[0]
    log.ok(f"detected {len(faces)} face(s); using the most prominent one")
    log.kv("face box (x,y,w,h)", face.box)
    log.kv("detector score", f"{face.score:.3f}")
    log.kv("embedding dim", len(face.embedding))
    log.kv("embedding sha256", face.embedding_sha256)
    annotated = config.ARTIFACTS_DIR / (Path(image_path).stem + "_annotated.jpg")
    try:
        recognizer.annotate(image_path, annotated, label="SCANNED FACE")
        log.kv("annotated image", annotated)
    except Exception as e:
        log.warn(f"could not save annotated image: {e}")

    # ---- STEP 2: social-media / web search --------------------------------
    resolved = search_base.resolve_provider_name(provider)
    log.step(f"Social/web search — provider: {resolved}")
    prov = search_base.get_provider(resolved, recognizer=recognizer)
    with log.timed("search"):
        post = prov.search(image_path, query_embedding=face.embedding)
    if post is None or not (post.url or post.image_url):
        raise PipelineError("search returned no matching post")
    log.ok("matching post discovered")
    log.kv("platform", post.platform)
    log.kv("post url", post.url or "(none)")
    log.kv("post title", (post.title or "")[:70])
    log.kv("match score (cosine)", post.match_score)
    log.kv("face verified", post.face_verified)

    # The offline index returns the *closest* entry; if it is below the identity
    # threshold this is not a confident match, so we stop rather than anchor a
    # weak guess. (Reverse-image hits from the live provider stay valid even when
    # a same-face thumbnail could not be re-fetched to confirm.)
    if resolved == "local" and not post.face_verified and not allow_unverified:
        raise PipelineError(
            f"no confident identity match (best cosine {post.match_score} < "
            f"{config.FACE_COSINE_THRESHOLD}). Use --allow-unverified to anchor anyway."
        )

    # ---- STEP 3: build tamper-evident fingerprint -------------------------
    log.step("Fingerprint — canonical record + keccak256")
    record = build_record(
        query_image_sha256=img_sha,
        face_embedding_sha256=face.embedding_sha256,
        face_embedding_b64=face.embedding_b64,
        post=post.to_dict(),
    )
    fingerprint = record["fingerprint"]
    log.kv("fingerprint (keccak256)", fingerprint)

    # ---- STEP 4: anchor on-chain ------------------------------------------
    log.step(f"Blockchain — anchor on chain: {chain}")
    ctx = connect_chain(chain)
    log.kv("network", ctx.name)
    log.kv("chain id", ctx.chain_id)
    log.kv("submitter", ctx.address)
    reg = FaceRegistry(ctx)
    saved = None if redeploy else FaceRegistry.saved_address(ctx.name)
    # eth-tester 'memory' chains are ephemeral, so a saved address is stale.
    if saved and ctx.name != "memory":
        log.info(f"attaching to existing contract {saved}")
        reg = FaceRegistry(ctx, address=saved)
    else:
        with log.timed("contract deploy"):
            addr = reg.deploy()
        log.ok(f"FaceRegistry deployed at {addr}")

    uri = post.url or f"facechain://{post.platform}/{post.image_sha256[:12]}"
    with log.timed("anchor tx"):
        anchor = reg.anchor(fingerprint, uri)
    if anchor.get("already_anchored"):
        log.warn("this exact fingerprint was already on-chain (idempotent)")
    else:
        log.ok("record anchored on-chain")
        log.kv("tx hash", anchor["tx_hash"])
        exp = ctx.explorer_tx(anchor["tx_hash"])
        if exp:
            log.kv("explorer", exp)
    log.kv("block", anchor["block"])
    log.kv("on-chain timestamp", anchor["timestamp"])
    log.kv("total records on-chain", reg.count())

    record["chain"] = {
        "network": ctx.name,
        "chain_id": ctx.chain_id,
        "contract": reg.address,
        "submitter": ctx.address,
        "tx_hash": anchor.get("tx_hash"),
        "block": anchor.get("block"),
        "on_chain_timestamp": anchor["timestamp"],
        "uri": anchor["uri"],
    }

    # ---- persist record ----------------------------------------------------
    record_path = config.RECORDS_DIR / f"record_{_short(fingerprint)}.json"
    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    log.kv("record saved", record_path)

    # ---- STEP 5: re-verify against the on-chain record --------------------
    log.step("Verify — re-read chain & recompute fingerprint")
    result = verify_record(record, live_registry=reg)
    _print_verification(result)

    return {
        "record_path": str(record_path),
        "record": record,
        "fingerprint": fingerprint,
        "post": post.to_dict(),
        "chain": record["chain"],
        "verification": result,
        "annotated_image": str(annotated) if annotated.exists() else None,
    }


def verify_record(record: dict, *, live_registry: Optional[FaceRegistry] = None,
                  tamper_field: Optional[str] = None) -> dict:
    """Independently verify a record against its on-chain anchor.

    * Recomputes the fingerprint from the record's canonical payload
      (integrity of the off-chain data).
    * Reads the ledger and confirms the fingerprint exists with a matching URI
      (integrity against the tamper-evident anchor).

    ``tamper_field`` (e.g. ``"match.url"``) mutates a copy of the payload before
    hashing, to demonstrate that tampering breaks verification.
    """
    payload = json.loads(json.dumps(record["fingerprint_payload"]))  # deep copy

    if tamper_field:
        section, _, key = tamper_field.partition(".")
        target = payload[section] if key else payload
        k = key or section
        orig = target.get(k)
        target[k] = (str(orig) + "_TAMPERED") if orig is not None else "TAMPERED"
        log.info(log.dim(f"simulating an attacker editing the '{tamper_field}' "
                         f"field of the saved record …"))

    recomputed = compute_fingerprint(payload)
    stored = record["fingerprint"]
    off_chain_ok = (recomputed == stored)

    checks = {
        "recomputed_fingerprint": recomputed,
        "stored_fingerprint": stored,
        "offchain_integrity": off_chain_ok,
    }

    chain_meta = record.get("chain") or {}
    checks["network"] = chain_meta.get("network")
    checks["contract"] = chain_meta.get("contract")

    # connect to the ledger (reuse a live registry if provided)
    reg = live_registry
    try:
        if reg is None:
            ctx = connect_chain(chain_meta.get("network"))
            if not chain_meta.get("contract"):
                raise RuntimeError("record has no contract address")
            reg = FaceRegistry(ctx, address=chain_meta["contract"])
        on = reg.read(recomputed)
        checks["onchain_exists"] = bool(on["exists"])
        checks["onchain_uri"] = on["uri"]
        checks["onchain_timestamp"] = on["timestamp"]
        checks["uri_matches"] = (on["uri"] == chain_meta.get("uri"))
        checks["chain_reachable"] = True
    except Exception as e:
        checks["chain_reachable"] = False
        checks["onchain_exists"] = False
        checks["uri_matches"] = False
        checks["chain_error"] = str(e)

    checks["verified"] = bool(
        off_chain_ok and checks.get("onchain_exists") and checks.get("uri_matches")
    )
    return checks


def _print_verification(checks: dict, tamper_mode: bool = False) -> None:
    def mark(b):
        return log.green("PASS") if b else log.red("FAIL")

    off = checks["offchain_integrity"]
    reachable = checks.get("chain_reachable")
    network = checks.get("network")

    # --- Tamper demo: an intentional mismatch is a SUCCESS. Show it all-green,
    #     with no red "FAIL" or scary warnings on screen. ------------------------
    if tamper_mode:
        log.kv("original fingerprint (anchored)", checks["stored_fingerprint"])
        log.kv("fingerprint after the edit", checks["recomputed_fingerprint"])
        if not off:
            log.ok("the edit changed the fingerprint — the change is detected")
            log.ok("an altered record can never match the on-chain anchor")
        else:
            log.warn("unexpected: the edit did not change the fingerprint")
        print()
        if not checks.get("verified"):
            log.banner("🛡️  TAMPER-EVIDENCE CONFIRMED",
                       "the altered record was correctly rejected by the ledger")
        else:
            log.banner("⚠️  TAMPER NOT DETECTED",
                       "a modified record still verified — this should not happen")
        return

    log.kv("off-chain integrity", mark(off))
    log.kv("  recomputed", checks["recomputed_fingerprint"])
    log.kv("  stored", checks["stored_fingerprint"])
    if not off:
        log.fail("fingerprint mismatch — the edit to the record was detected")

    if reachable:
        log.kv("on-chain fingerprint exists", mark(checks.get("onchain_exists")))
        log.kv("on-chain uri matches", mark(checks.get("uri_matches")))
        if checks.get("onchain_exists"):
            log.kv("  on-chain uri", checks.get("onchain_uri"))
            log.kv("  on-chain timestamp", checks.get("onchain_timestamp"))
    elif network == "memory":
        log.info(log.dim("on-chain re-read skipped — the in-process 'memory' chain is "
                         "ephemeral; the off-chain fingerprint check above is authoritative."))
    else:
        log.warn(f"chain not reachable for re-read: {checks.get('chain_error')}")

    print()
    if not off:
        log.banner("❌  VERIFICATION FAILED — RECORD ALTERED",
                   "record contents no longer match the anchored fingerprint")
    elif reachable and checks.get("verified"):
        log.banner("✅  VERIFIED ON-CHAIN",
                   "record integrity confirmed against the tamper-evident ledger")
    elif not reachable and network == "memory":
        log.banner("✅  OFF-CHAIN INTEGRITY OK",
                   "fingerprint intact; on-chain re-read needs --chain rpc or sepolia")
    else:
        log.banner("❌  VERIFICATION FAILED",
                   "record does not match the on-chain anchor")
