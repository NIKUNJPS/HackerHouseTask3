"""Upload an image to a temporary public host so a reverse-image API can fetch it.

Only used by the SerpApi provider (Google Lens fetches the image by URL).
Tries several hosts in order and returns the first URL that is actually
fetchable as an image. Returns a public https URL.

Privacy note: this publishes the input image to a third-party host. It is only
invoked on the live-web search path (--provider serpapi). The offline
local-index path never uploads anything.
"""
from __future__ import annotations

import re
from pathlib import Path

import requests

# A realistic browser UA — several hosts now reject obvious bot/library agents.
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/124.0 Safari/537.36"}


def _safe_name(path: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]", "", path.stem)[:32] or "upload"
    ext = path.suffix.lower() if path.suffix.lower() in (
        ".jpg", ".jpeg", ".png", ".webp", ".bmp") else ".jpg"
    return stem + ext


def _reachable(url: str) -> bool:
    """Confirm the URL serves image bytes (so Google Lens can fetch it)."""
    try:
        r = requests.get(url, headers=_UA, timeout=45, stream=True)
        ok = r.status_code == 200 and \
            "image" in r.headers.get("content-type", "").lower()
        r.close()
        return ok
    except Exception:
        return False


def _uguu(path: Path) -> str:
    with open(path, "rb") as f:
        r = requests.post("https://uguu.se/upload.php",
                          files={"files[]": (_safe_name(path), f, "image/jpeg")},
                          headers=_UA, timeout=90)
    r.raise_for_status()
    j = r.json()
    if not j.get("success"):
        raise RuntimeError(f"uguu rejected upload: {j}")
    return j["files"][0]["url"]


def _tmpfiles(path: Path) -> str:
    with open(path, "rb") as f:
        r = requests.post("https://tmpfiles.org/api/v1/upload",
                          files={"file": (_safe_name(path), f, "image/jpeg")},
                          headers=_UA, timeout=90)
    r.raise_for_status()
    url = r.json()["data"]["url"]
    # The API returns a viewer page URL; the direct file is under /dl/.
    return url.replace("tmpfiles.org/", "tmpfiles.org/dl/", 1)


def _catbox(path: Path) -> str:
    with open(path, "rb") as f:
        r = requests.post("https://catbox.moe/user/api.php",
                          data={"reqtype": "fileupload"},
                          files={"fileToUpload": (_safe_name(path), f)},
                          headers=_UA, timeout=90)
    r.raise_for_status()
    url = r.text.strip()
    if not url.startswith("http"):
        raise RuntimeError(f"catbox unexpected response: {url[:120]!r}")
    return url


def upload_public(path: str | Path) -> str:
    path = Path(path)
    errors = []
    for fn in (_uguu, _tmpfiles, _catbox):
        try:
            url = fn(path)
            if _reachable(url):
                return url
            errors.append(f"{fn.__name__}: returned unfetchable url {url}")
        except Exception as e:  # try the next host
            errors.append(f"{fn.__name__}: {e}")
    raise RuntimeError("could not upload image to any public host:\n  " +
                       "\n  ".join(errors))
