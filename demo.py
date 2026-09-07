#!/usr/bin/env python
"""One-command, recording-friendly walkthrough of the whole pipeline.

    python demo.py                         # default sample image
    python demo.py --pause                 # wait for Enter between steps (for narration)
    python demo.py img1.jpg img2.jpg ...   # run on your own images, back to back
    python demo.py --no-tamper             # skip the tamper-evidence step

For each image it runs:  FACE SCAN -> SOCIAL/WEB SEARCH -> BLOCKCHAIN ANCHOR + VERIFY.
It uses the LIVE web search (SerpApi Google Lens) when SERPAPI_KEY is set, else the
offline face-embedding index. Finally it runs a tamper-evidence test that proves an
edited record is rejected by the ledger.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
ARGV = sys.argv[1:]
PAUSE = "--pause" in ARGV
TAMPER = "--no-tamper" not in ARGV
IMAGES = [a for a in ARGV if not a.startswith("--")]

DEFAULT_SCAN = "samples/scan_person_a.jpg"


def banner(title: str) -> None:
    print("\n" + "█" * 72)
    print("██  " + title)
    print("█" * 72, flush=True)


def wait(msg: str = "press Enter to continue") -> None:
    if PAUSE:
        try:
            input(f"   [{msg}] ")
        except EOFError:
            pass


def cli(args: list[str], title: str) -> int:
    banner(title)
    print("   $ python cli.py " + " ".join(args) + "\n", flush=True)
    wait("press Enter to run this step")
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
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass

    use_live = bool(os.environ.get("SERPAPI_KEY", "").strip())
    provider = "serpapi" if use_live else "local"
    src = "LIVE WEB — SerpApi Google Lens" if use_live else "OFFLINE face-embedding index"

    images = IMAGES or [DEFAULT_SCAN]

    # Ensure the bundled sample exists if we're going to use it.
    if DEFAULT_SCAN in images and not (ROOT / DEFAULT_SCAN).exists():
        if cli(["make-sample"], "SETUP  —  download a sample face scan input"):
            return 1
    # The offline index is only needed for the local provider.
    if not use_live:
        if not (ROOT / "dataset" / "sources.json").exists():
            if cli(["make-sample"], "SETUP  —  prepare demo dataset"):
                return 1
        cli(["build-index"], "SETUP  —  build the offline face index")

    banner("FACECHAIN DEMO  —  %d image(s)   |   search backend: %s" % (len(images), src))
    wait("press Enter to begin")

    for i, img in enumerate(images, 1):
        banner("IMAGE %d/%d  —  FACE SCAN -> SOCIAL SEARCH -> BLOCKCHAIN   |   %s"
               % (i, len(images), img))
        print("   $ python cli.py run --image %s --provider %s --chain memory\n"
              % (img, provider), flush=True)
        wait("press Enter to run the pipeline on this image")
        subprocess.run([PY, "cli.py", "run", "--image", img,
                        "--provider", provider, "--chain", "memory"], cwd=ROOT)

    if TAMPER:
        rec = newest_record()
        banner("TAMPER-EVIDENCE TEST  —  prove a faked record is rejected")
        print("   (we edit one field of the saved record; the ledger must reject it)")
        print("   $ python cli.py verify --record %s --tamper match.url\n" % rec, flush=True)
        wait("press Enter to run the tamper-evidence test")
        subprocess.run([PY, "cli.py", "verify", "--record", rec,
                        "--tamper", "match.url"], cwd=ROOT)

    banner("DEMO COMPLETE  —  faces scanned, real posts found, records anchored & verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
