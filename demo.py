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


def record_set() -> set[Path]:
    return set((ROOT / "data" / "records").glob("record_*.json"))


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT)).replace("\\", "/")


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

    before = record_set()
    successes = 0
    for i, img in enumerate(images, 1):
        banner("IMAGE %d/%d  —  FACE SCAN -> SOCIAL SEARCH -> BLOCKCHAIN   |   %s"
               % (i, len(images), img))
        print("   $ python cli.py run --image %s --provider %s --chain memory\n"
              % (img, provider), flush=True)
        wait("press Enter to run the pipeline on this image")
        rc = subprocess.run([PY, "cli.py", "run", "--image", img,
                             "--provider", provider, "--chain", "memory"],
                            cwd=ROOT).returncode
        if rc == 0:
            successes += 1
        else:
            print("\n   (this image produced no verified match — continuing)\n", flush=True)

    # Only tamper-test a record created during THIS run — never a stale one.
    new_records = sorted(record_set() - before, key=lambda p: p.stat().st_mtime)
    if TAMPER and new_records:
        rec = rel(new_records[-1])
        banner("TAMPER-EVIDENCE TEST  —  prove a faked record is rejected")
        print("   (we edit one field of the saved record; the ledger must reject it)")
        print("   $ python cli.py verify --record %s --tamper match.url\n" % rec, flush=True)
        wait("press Enter to run the tamper-evidence test")
        subprocess.run([PY, "cli.py", "verify", "--record", rec,
                        "--tamper", "match.url"], cwd=ROOT)
    elif TAMPER:
        banner("TAMPER-EVIDENCE TEST  —  skipped")
        print("   No new record was produced (the search step did not complete),")
        print("   so there is nothing fresh to tamper-test. See the errors above.")

    if successes == 0:
        banner("DEMO INCOMPLETE  —  no image produced a verified on-chain record")
        return 1
    banner("DEMO COMPLETE  —  %d/%d image(s) scanned, matched, anchored & verified"
           % (successes, len(images)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
