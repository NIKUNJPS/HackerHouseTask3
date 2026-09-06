"""Offline, genuine face-embedding search over a self-built social-media index.

This is a real nearest-neighbour identity search — NOT a hard-coded result:

* ``dataset/`` holds real social-media images, each paired (in
  ``dataset/sources.json``) with the real URL of the post it came from.
* ``build()`` detects + embeds the face in every dataset image and stores the
  128-D vectors.
* ``search(query_embedding)`` returns the post whose face is closest to the
  scanned face (cosine similarity), gated by a threshold — so an unknown face
  correctly returns *no match*.

Used automatically when no ``SERPAPI_KEY`` is configured, and as a reliable
offline path for demos.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np

from .. import config, log
from .base import SearchProvider, SocialPost, sha256_bytes

_INDEX_NPZ = config.ARTIFACTS_DIR / "local_index.npz"
_INDEX_JSON = config.ARTIFACTS_DIR / "local_index.json"
_SOURCES = "sources.json"
_IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class LocalIndexProvider(SearchProvider):
    name = "local"

    def __init__(self, recognizer=None):
        self._recognizer = recognizer
        self._embeddings: Optional[np.ndarray] = None
        self._meta: list[dict] = []
        if _INDEX_NPZ.exists() and _INDEX_JSON.exists():
            self._load()

    # -- build ---------------------------------------------------------------
    def build(self, dataset_dir: str | Path = None) -> int:
        """(Re)build the index from a dataset directory. Returns #entries."""
        if self._recognizer is None:
            from ..face import FaceRecognizer
            self._recognizer = FaceRecognizer()

        dataset_dir = Path(dataset_dir or config.DATASET_DIR)
        sources_path = dataset_dir / _SOURCES
        sources = {}
        if sources_path.exists():
            sources = json.loads(sources_path.read_text(encoding="utf-8"))

        vectors, meta = [], []
        for img in sorted(dataset_dir.iterdir()):
            if img.suffix.lower() not in _IMG_EXTS:
                continue
            try:
                face = self._recognizer.primary_face(img)
            except Exception as e:
                log.warn(f"skip {img.name}: {e}")
                continue
            src = sources.get(img.name, {})
            vectors.append(face.embedding.astype(np.float32))
            meta.append({
                "file": img.name,
                "image_sha256": sha256_bytes(img.read_bytes()),
                "url": src.get("url", ""),
                "platform": src.get("platform", ""),
                "title": src.get("title", ""),
                "handle": src.get("handle", ""),
            })
            log.info(f"indexed {img.name}  ->  {src.get('url', '(no source url)')}")

        if not vectors:
            raise RuntimeError(
                f"no usable face images found in {dataset_dir}. Add images and a "
                f"{_SOURCES} mapping, or run scripts/make_sample_dataset.py."
            )

        self._embeddings = np.vstack(vectors)
        self._meta = meta
        np.savez_compressed(_INDEX_NPZ, embeddings=self._embeddings)
        _INDEX_JSON.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        log.ok(f"local index built: {len(meta)} entries -> {_INDEX_NPZ.name}")
        return len(meta)

    def _load(self) -> None:
        self._embeddings = np.load(_INDEX_NPZ)["embeddings"]
        self._meta = json.loads(_INDEX_JSON.read_text(encoding="utf-8"))

    # -- search --------------------------------------------------------------
    def search(self, image_path: str, query_embedding=None) -> Optional[SocialPost]:
        if self._embeddings is None or not self._meta:
            raise RuntimeError(
                "local index is empty. Build it first:  python cli.py build-index"
            )
        if query_embedding is None:
            from ..face import FaceRecognizer
            rec = self._recognizer or FaceRecognizer()
            query_embedding = rec.primary_face(image_path).embedding

        q = np.asarray(query_embedding, dtype=np.float64).flatten()
        M = self._embeddings.astype(np.float64)
        sims = (M @ q) / (np.linalg.norm(M, axis=1) * np.linalg.norm(q) + 1e-12)
        idx = int(np.argmax(sims))
        score = float(sims[idx])
        m = self._meta[idx]
        log.kv("closest entry", f"{m['file']}  (cos={score:.4f})")

        verified = score >= config.FACE_COSINE_THRESHOLD
        if not verified:
            log.warn(f"best match below identity threshold "
                     f"({score:.3f} < {config.FACE_COSINE_THRESHOLD}) — no confident match")
        return SocialPost(
            url=m["url"],
            platform=m["platform"] or "unknown",
            title=m["title"],
            image_url=m["file"],
            image_sha256=m["image_sha256"],
            match_score=round(score, 4),
            face_verified=verified,
            provider=self.name,
            raw=m,
        )
