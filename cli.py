#!/usr/bin/env python
"""FaceChain command-line interface.

    python cli.py run --image samples/scan_obama.jpg --provider local --chain memory
    python cli.py verify --record data/records/record_XXXX.json
    python cli.py verify --record data/records/record_XXXX.json --tamper match.url
    python cli.py build-index --dataset dataset
    python cli.py make-sample
    python cli.py info
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from facechain import config, log
from facechain import pipeline
from facechain.search.local_index import LocalIndexProvider


def cmd_run(args) -> int:
    try:
        result = pipeline.run(
            args.image, provider=args.provider, chain=args.chain,
            redeploy=args.redeploy, allow_unverified=args.allow_unverified,
        )
    except pipeline.PipelineError as e:
        log.fail(str(e))
        return 2
    if args.json:
        # trim big base64 blob for readability
        r = json.loads(json.dumps(result))
        r["record"]["query"].pop("face_embedding_b64", None)
        print(json.dumps(r, indent=2))
    verified = result["verification"]["verified"]
    return 0 if verified else 3


def cmd_verify(args) -> int:
    record = json.loads(Path(args.record).read_text(encoding="utf-8"))
    log.banner("FaceChain — Verify record against the ledger",
               Path(args.record).name)
    checks = pipeline.verify_record(record, tamper_field=args.tamper)
    pipeline._print_verification(checks)
    if args.json:
        print(json.dumps(checks, indent=2))
    if args.tamper:
        # For a tamper demo, success means verification correctly FAILED.
        return 0 if not checks["verified"] else 4
    return 0 if checks["verified"] else 3


def cmd_build_index(args) -> int:
    prov = LocalIndexProvider()
    n = prov.build(args.dataset)
    log.ok(f"index ready with {n} entries")
    return 0


def cmd_make_sample(args) -> int:
    from scripts.make_sample_dataset import make_sample
    make_sample()
    return 0


def cmd_info(args) -> int:
    log.banner("FaceChain configuration")
    for k, v in config.summary().items():
        log.kv(k, v)
    print()
    log.info("Search provider that will be used by --provider auto: "
             + ("serpapi (live web)" if config.SERPAPI_KEY else "local (offline index)"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="facechain",
        description="Face scan -> social-media search -> blockchain verification.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run the full pipeline on an image")
    r.add_argument("--image", required=True, help="path to the face scan image")
    r.add_argument("--provider", default="auto",
                   choices=["auto", "serpapi", "local"],
                   help="search backend (default: auto)")
    r.add_argument("--chain", default=None,
                   help="blockchain: memory | rpc | sepolia (default: env/memory)")
    r.add_argument("--redeploy", action="store_true",
                   help="deploy a fresh contract instead of reusing a saved one")
    r.add_argument("--allow-unverified", action="store_true",
                   help="anchor even a low-confidence (below-threshold) local match")
    r.add_argument("--json", action="store_true", help="print machine-readable result")
    r.set_defaults(func=cmd_run)

    v = sub.add_parser("verify", help="re-verify a saved record against the chain")
    v.add_argument("--record", required=True, help="path to a data/records/*.json file")
    v.add_argument("--tamper", default=None,
                   help="mutate a payload field (e.g. match.url) to prove tamper-evidence")
    v.add_argument("--json", action="store_true")
    v.set_defaults(func=cmd_verify)

    b = sub.add_parser("build-index", help="build the offline local face index")
    b.add_argument("--dataset", default=str(config.DATASET_DIR))
    b.set_defaults(func=cmd_build_index)

    s = sub.add_parser("make-sample", help="download a runnable demo dataset + input")
    s.set_defaults(func=cmd_make_sample)

    i = sub.add_parser("info", help="show configuration")
    i.set_defaults(func=cmd_info)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        log.warn("interrupted")
        return 130
    except Exception as e:  # surface a clean error, full trace with -v env
        log.fail(f"{type(e).__name__}: {e}")
        import os
        if os.environ.get("FACECHAIN_DEBUG"):
            raise
        return 1


if __name__ == "__main__":
    sys.exit(main())
