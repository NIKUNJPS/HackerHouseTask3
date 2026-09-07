"""Live web / social-media reverse-image search via SerpApi's Google Lens engine.

Flow:
    1. Publish the input image to a temporary public host (Google Lens fetches
       images by URL).
    2. Query SerpApi's ``google_lens`` engine to get real visual matches from
       across the web (pages that contain the image).
    3. Keep the ones hosted on social-media domains.
    4. Face-verify each candidate: download its thumbnail, re-embed the face and
       compare to the query embedding. Rank by cosine similarity so the returned
       post is a confirmed *identity* match, not merely a page that links the
       image.

Requires a (free-tier) SerpApi key in ``SERPAPI_KEY``.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

import requests

from .. import config, log
from .base import (SearchProvider, SocialPost, is_social_url, platform_of,
                   sha256_bytes)
from .uploader import upload_public

_UA = {"User-Agent": "facechain/1.0"}


class SerpApiProvider(SearchProvider):
    name = "serpapi"

    def __init__(self, recognizer=None):
        if not config.SERPAPI_KEY:
            raise RuntimeError(
                "SERPAPI_KEY is not set. Get a free key at serpapi.com and put "
                "it in your environment or .env, or use --provider local."
            )
        self._recognizer = recognizer

    # -- helpers -------------------------------------------------------------
    def _lens(self, image_url: str) -> list[dict]:
        params = {
            "engine": "google_lens",
            "url": image_url,
            "api_key": config.SERPAPI_KEY,
        }
        r = requests.get("https://serpapi.com/search.json", params=params,
                         timeout=90)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(f"SerpApi error: {data['error']}")
        return data.get("visual_matches", []) or []

    def _embed_url(self, image_url: str) -> tuple[Optional[object], str]:
        """Download an image URL and return (embedding | None, sha256)."""
        try:
            r = requests.get(image_url, headers=_UA, timeout=45)
            r.raise_for_status()
            blob = r.content
        except Exception:
            return None, ""
        digest = sha256_bytes(blob)
        if self._recognizer is None:
            return None, digest
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(blob)
            tmp_path = tmp.name
        try:
            faces = self._recognizer.detect_faces(tmp_path)
            emb = faces[0].embedding if faces else None
        except Exception:
            emb = None
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        return emb, digest

    # -- api -----------------------------------------------------------------
    def search(self, image_path: str, query_embedding=None) -> Optional[SocialPost]:
        log.info("publishing image to a temporary public host for Google Lens …")
        public_url = upload_public(image_path)
        log.kv("public image url", public_url)

        log.info("querying SerpApi Google Lens (live web reverse image search) …")
        matches = self._lens(public_url)
        log.kv("raw visual matches", len(matches))

        social = [m for m in matches if is_social_url(m.get("link", ""))]
        log.kv("social-media candidates", len(social))
        if not social:
            # No social hits — fall back to the single best overall visual match
            # so the pipeline still has a real, discovered result to anchor.
            if not matches:
                return None
            social = matches[:5]

        from .base import cosine_or_zero  # local import to avoid cycle at top

        candidates: list[SocialPost] = []
        for m in social[:12]:
            link = m.get("link", "")
            thumb = m.get("thumbnail", "") or m.get("image", "")
            emb, digest = self._embed_url(thumb) if thumb else (None, "")
            score = 0.0
            verified = False
            if emb is not None and query_embedding is not None:
                score = cosine_or_zero(query_embedding, emb)
                verified = score >= config.SEARCH_MATCH_THRESHOLD
            candidates.append(SocialPost(
                url=link,
                platform=platform_of(link),
                title=m.get("title", "") or m.get("source", ""),
                image_url=thumb,
                image_sha256=digest,
                match_score=round(score, 4),
                face_verified=verified,
                provider=self.name,
                raw=m,
            ))

        # Rank every discovered social post by face similarity and show them all,
        # so the demo surfaces each platform the live web actually returned
        # (Instagram, Facebook, X, Pinterest, …) — none of it hard-coded.
        candidates.sort(key=lambda p: p.match_score, reverse=True)
        if candidates:
            log.info("social-media posts found on the live web (ranked by face match):")
            for p in candidates[:8]:
                tick = "verified" if p.face_verified else "  —     "
                log.kv(f"  [{tick}] {p.platform:<10} cos={p.match_score:.3f}", p.url[:66])

        # Record every match on the fingerprint record for auditability.
        best = candidates[0] if candidates else None
        if best is not None:
            best.raw = dict(best.raw or {})
            best.raw["all_social_matches"] = [
                {"platform": p.platform, "url": p.url,
                 "match_score": p.match_score, "face_verified": p.face_verified}
                for p in candidates[:8]
            ]
        return best
