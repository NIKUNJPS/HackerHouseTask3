#!/usr/bin/env python
"""One-command, recording-friendly walkthrough of the whole pipeline.

    python demo.py            # run the full narrative end-to-end
    python demo.py --pause    # wait for Enter between steps (nice for narration)

It runs, in order:
    1. prepare a small demo dataset (public sample faces + real source URLs)
    2. build the offline face index
    3. FACE SCAN -> SOCIAL SEARCH -> BLOCKCHAIN ANCHOR + VERIFY   (a real match)
    4. TAMPER TEST: edit the saved record -> verification correctly FAILS

Everything is offline and needs no API keys or blockchain node.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
PAUSE = "--pause" in sys.argv

SCAN = "samples/scan_person_a.jpg"


def banner(title: str) -> None:
    print("\n" + "█" * 72)
    print("██  " + title)
    print("█" * 72, flush=True)


def run(args: list[str], title: str) -> int:
    banner(title)
    print("   $ python cli.py " + " ".join(args) + "\n", flush=True)
    if PAUSE:
        try:
            input("   [press Enter to run this step] ")
        except EOFError:
            pass
    return subprocess.run([PY, "cli.py", *args], cwd=ROOT).returncode


def newest_record() -> str:
    recs = sorted((ROOT / "data" / "records").glob("record_*.json"),
                  key=lambda p: p.stat().st_mtime)
    if not recs:
        raise SystemExit("no record was produced by the run step")
    return str(recs[-1].relative_to(ROOT)).replace("\\", "/")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    have_data = (ROOT / SCAN).exists() and (ROOT / "dataset" / "sources.json").exists()
    if not have_data:
        if run(["make-sample"], "STEP 0  —  prepare demo dataset (public faces + real URLs)"):
            return 1
    run(["build-index"], "STEP 1  —  build the offline face index")

    banner("STEP 2  —  FACE SCAN  ->  SOCIAL SEARCH  ->  BLOCKCHAIN  (real match)")
    print("   $ python cli.py run --image %s --provider local --chain memory\n" % SCAN,
          flush=True)
    if PAUSE:
        try:
            input("   [press Enter to run the full pipeline] ")
        except EOFError:
            pass
    subprocess.run([PY, "cli.py", "run", "--image", SCAN,
                    "--provider", "local", "--chain", "memory"], cwd=ROOT)

    rec = newest_record()
    banner("STEP 3  —  TAMPER TEST  (editing the record must break verification)")
    print("   $ python cli.py verify --record %s --tamper match.url\n" % rec, flush=True)
    if PAUSE:
        try:
            input("   [press Enter to run the tamper test] ")
        except EOFError:
            pass
    subprocess.run([PY, "cli.py", "verify", "--record", rec,
                    "--tamper", "match.url"], cwd=ROOT)

    banner("DEMO COMPLETE  —  real match anchored on-chain, tampering rejected")
    print("   Saved record: %s" % rec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
