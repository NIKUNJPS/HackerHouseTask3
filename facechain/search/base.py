"""Search provider interface + the normalised result type.

A *genuine* search step turns a face into at least one real, matching
social-media post. Two interchangeable providers implement this:

* :class:`~facechain.search.serpapi_provider.SerpApiProvider` — live reverse
  image search of the web via SerpApi's Google Lens engine, then face-verifies
  each candidate by re-embedding its thumbnail.
* :class:`~facechain.search.local_index.LocalIndexProvider` — an offline
  nearest-neighbour search over a self-built index of real social-media images
  (each with its real source URL). Uses the same face embeddings, so it is a
  true identity match, not a hard-coded result.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional
from urllib.parse import urlparse

from .. import config


def is_social_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    host = host[4:] if host.startswith("www.") else host
    return any(host == d or host.endswith("." + d) for d in config.SOCIAL_DOMAINS)


def platform_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return "unknown"
    host = host[4:] if host.startswith("www.") else host
    for d in config.SOCIAL_DOMAINS:
        if host == d or host.endswith("." + d):
            return d.split(".")[0]
    return host or "unknown"


@dataclass
class SocialPost:
    """A single matching post discovered by a search provider."""

    url: str
    platform: str
    title: str = ""
    image_url: str = ""              # the image shown on the post (if known)
    image_sha256: str = ""           # sha256 of the fetched image bytes
    match_score: float = 0.0         # face cosine similarity (0..1) if verified
    face_verified: bool = False      # did we re-embed & confirm the same face?
    provider: str = ""
    raw: dict = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("raw", None)
        return d


class SearchProvider:
    name = "base"

    def search(self, image_path: str, query_embedding=None) -> Optional[SocialPost]:
        """Return the best matching :class:`SocialPost`, or ``None``."""
        raise NotImplementedError


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def cosine_or_zero(a, b) -> float:
    """Cosine similarity that tolerates ``None`` inputs (returns 0.0)."""
    if a is None or b is None:
        return 0.0
    from ..face.recognizer import cosine
    return cosine(a, b)


def resolve_provider_name(name: str) -> str:
    name = (name or "auto").lower()
    if name == "auto":
        name = "serpapi" if config.SERPAPI_KEY else "local"
    return name


def get_provider(name: str, recognizer=None) -> SearchProvider:
    """Factory. ``name`` in {auto, serpapi, local}.

    ``recognizer`` (a :class:`~facechain.face.FaceRecognizer`) is injected so a
    provider can face-verify candidate images without reloading the models.
    """
    name = resolve_provider_name(name)

    if name == "serpapi":
        from .serpapi_provider import SerpApiProvider
        return SerpApiProvider(recognizer=recognizer)
    if name == "local":
        from .local_index import LocalIndexProvider
        return LocalIndexProvider(recognizer=recognizer)
    raise ValueError(f"unknown search provider: {name!r}")
