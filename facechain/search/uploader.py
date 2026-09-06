"""Upload an image to a temporary public host so a reverse-image API can fetch it.

Only used by the SerpApi provider (Google Lens fetches the image by URL).
Tries catbox.moe first, then 0x0.st. Returns a public https URL.

Privacy note: this publishes the input image to a third-party host. It is only
invoked on the live-web search path (--provider serpapi). The offline
local-index path never uploads anything.
"""
from __future__ import annotations

from pathlib import Path

import requests

_UA = {"User-Agent": "facechain/1.0 (reverse-image-search)"}


def _catbox(path: Path) -> str:
    with open(path, "rb") as f:
        r = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": (path.name, f)},
            headers=_UA,
            timeout=90,
        )
    r.raise_for_status()
    url = r.text.strip()
    if not url.startswith("http"):
        raise RuntimeError(f"catbox unexpected response: {url[:120]!r}")
    return url


def _zerox(path: Path) -> str:
    with open(path, "rb") as f:
        r = requests.post("https://0x0.st", files={"file": (path.name, f)},
                          headers=_UA, timeout=90)
    r.raise_for_status()
    url = r.text.strip()
    if not url.startswith("http"):
        raise RuntimeError(f"0x0.st unexpected response: {url[:120]!r}")
    return url


def upload_public(path: str | Path) -> str:
    path = Path(path)
    errors = []
    for fn in (_catbox, _zerox):
        try:
            return fn(path)
        except Exception as e:  # try the next host
            errors.append(f"{fn.__name__}: {e}")
    raise RuntimeError("could not upload image to any public host:\n  " +
                       "\n  ".join(errors))
