"""Download a small, runnable demo dataset + a sample scan input.

This makes the offline pipeline work out-of-the-box for a demo/recording, using
well-known public sample face images. Each indexed image is paired with its REAL
public source URL (the face_recognition examples repo on GitHub), so the search
step returns a genuine, verifiable source — not a fabricated one.

The scan input (``samples/scan_obama.jpg``) is a *different* photo of the same
person than the one in the index, which demonstrates real cross-photo face
identification (not mere same-file image matching).

For real-world use, replace ``dataset/`` with your own social-media images and a
``dataset/sources.json`` mapping each file to its real post URL, then rebuild the
index. See the README.
"""
from __future__ import annotations

import json
from pathlib import Path

import requests

from facechain import config, log

_RAW = "https://raw.githubusercontent.com/ageitgey/face_recognition/master/examples/"
_BLOB = "https://github.com/ageitgey/face_recognition/blob/master/examples/"

# indexed image (local name) -> (download file, source metadata)
_INDEX = {
    "person_a_portrait.jpg": {
        "src_file": "obama2.jpg",
        "platform": "github",
        "url": _BLOB + "obama2.jpg",
        "title": "Public sample portrait A (44th US President) — face_recognition examples",
        "handle": "@ageitgey",
    },
    "person_b_portrait.jpg": {
        "src_file": "biden.jpg",
        "platform": "github",
        "url": _BLOB + "biden.jpg",
        "title": "Public sample portrait B (46th US President) — face_recognition examples",
        "handle": "@ageitgey",
    },
}
# scan input (a DIFFERENT photo of person A)
_SCAN = ("obama.jpg", config.ROOT / "samples" / "scan_person_a.jpg")


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    dest.write_bytes(r.content)
    log.kv("downloaded", f"{dest}  ({len(r.content)} bytes)")


def make_sample() -> None:
    log.banner("Preparing demo dataset", "public sample faces + real source URLs")
    ds = config.DATASET_DIR
    ds.mkdir(parents=True, exist_ok=True)

    sources = {}
    for local_name, meta in _INDEX.items():
        _download(_RAW + meta["src_file"], ds / local_name)
        sources[local_name] = {k: meta[k] for k in ("platform", "url", "title", "handle")}

    (ds / "sources.json").write_text(json.dumps(sources, indent=2), encoding="utf-8")
    log.ok(f"wrote {ds / 'sources.json'} with {len(sources)} sources")

    _download(_RAW + _SCAN[0], _SCAN[1])
    log.ok(f"sample scan input ready: {_SCAN[1]}")

    print()
    log.info("Next steps:")
    log.info("  python cli.py build-index")
    log.info("  python cli.py run --image samples/scan_person_a.jpg --provider local --chain memory")


if __name__ == "__main__":
    make_sample()
