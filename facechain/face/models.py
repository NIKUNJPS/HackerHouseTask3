"""Download and integrity-check the OpenCV face models on first use."""
from __future__ import annotations

import hashlib
from pathlib import Path

import requests

from .. import config
from .. import log


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_one(spec: dict) -> Path:
    dest = config.MODELS_DIR / spec["filename"]
    if dest.exists() and _sha256(dest) == spec["sha256"]:
        return dest

    log.info(f"downloading model {spec['filename']} …")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(spec["url"], stream=True, timeout=180) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        tmp.replace(dest)

    got = _sha256(dest)
    if got != spec["sha256"]:
        dest.unlink(missing_ok=True)
        raise RuntimeError(
            f"integrity check failed for {spec['filename']}: "
            f"expected {spec['sha256']}, got {got}"
        )
    log.ok(f"model ready: {spec['filename']}")
    return dest


def ensure_models() -> tuple[Path, Path]:
    """Return (detector_path, recognizer_path), downloading if needed."""
    det = _ensure_one(config.MODELS["detector"])
    rec = _ensure_one(config.MODELS["recognizer"])
    return det, rec
