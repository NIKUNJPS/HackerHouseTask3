"""Central configuration for FaceChain.

Values come from (in order of precedence): explicit function arguments,
environment variables (optionally loaded from a local ``.env`` file), then the
defaults below. Nothing secret is hard-coded here.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---- optional .env loading (no hard dependency) ---------------------------
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("FACECHAIN_DATA_DIR", ROOT / "data"))
MODELS_DIR = Path(os.environ.get("FACECHAIN_MODELS_DIR", ROOT / "models"))
DATASET_DIR = Path(os.environ.get("FACECHAIN_DATASET_DIR", ROOT / "dataset"))

RECORDS_DIR = DATA_DIR / "records"
ARTIFACTS_DIR = DATA_DIR / "artifacts"          # compiled ABI/bin, annotated images
DEPLOYMENTS_DIR = DATA_DIR / "deployments"

for _d in (DATA_DIR, MODELS_DIR, RECORDS_DIR, ARTIFACTS_DIR, DEPLOYMENTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ---- face models (OpenCV Zoo, pinned by sha256) ---------------------------
# Downloaded on first use and integrity-checked. Served from GitHub's LFS media
# endpoint so the real binaries (not LFS pointers) are fetched.
MODELS = {
    "detector": {
        "filename": "face_detection_yunet_2023mar.onnx",
        "url": "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
               "models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "sha256": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    },
    "recognizer": {
        "filename": "face_recognition_sface_2021dec.onnx",
        "url": "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
               "models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "sha256": "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    },
}

# SFace cosine similarity threshold. OpenCV's reference value is 0.363; a face is
# considered the same identity when cosine similarity is above this.
FACE_COSINE_THRESHOLD = float(os.environ.get("FACECHAIN_FACE_THRESHOLD", "0.363"))
# Detection confidence for YuNet.
FACE_DETECT_SCORE = float(os.environ.get("FACECHAIN_DETECT_SCORE", "0.7"))


# ---- search ----------------------------------------------------------------
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "").strip()

# Domains we treat as "social media / social web" when filtering search results.
SOCIAL_DOMAINS = [
    "instagram.com", "twitter.com", "x.com", "facebook.com", "fb.com",
    "linkedin.com", "tiktok.com", "reddit.com", "youtube.com", "youtu.be",
    "pinterest.com", "tumblr.com", "flickr.com", "vk.com", "threads.net",
    "mastodon.social", "github.com", "medium.com", "snapchat.com",
]

# Minimum face similarity for a discovered post to count as a confirmed match
# when we are able to fetch and compare the candidate's image.
SEARCH_MATCH_THRESHOLD = float(os.environ.get("FACECHAIN_SEARCH_THRESHOLD", "0.30"))


# ---- blockchain ------------------------------------------------------------
# Chain selection: "memory" (in-process EVM, zero setup), or any JSON-RPC node
# such as a local ganache/anvil ("rpc") or the public Sepolia testnet.
DEFAULT_CHAIN = os.environ.get("FACECHAIN_CHAIN", "memory")

# Generic JSON-RPC endpoint (ganache / anvil / hardhat / custom). Used for
# --chain rpc.
RPC_URL = os.environ.get("RPC_URL", "http://127.0.0.1:8545")

# Sepolia public testnet endpoint (e.g. Alchemy/Infura). Used for --chain sepolia.
SEPOLIA_RPC_URL = os.environ.get("SEPOLIA_RPC_URL", "").strip()

# Private key for signing transactions on any remote node (0x-prefixed hex).
# Never commit a real key. For a deterministic local ganache you can leave this
# blank and the first deterministic dev account is used automatically.
PRIVATE_KEY = os.environ.get("PRIVATE_KEY", "").strip()

# Deterministic mnemonic used by `ganache --wallet.deterministic` / hardhat.
# Lets --chain rpc work out of the box against a local dev node with no key set.
DEV_MNEMONIC = os.environ.get(
    "DEV_MNEMONIC",
    "test test test test test test test test test test test junk",
)

SOLC_VERSION = os.environ.get("SOLC_VERSION", "0.8.24")


def summary() -> dict:
    """A redacted view of the current configuration for `cli.py info`."""
    def redact(v: str) -> str:
        return (v[:6] + "…" + str(len(v)) + "chars") if v else "(unset)"

    return {
        "root": str(ROOT),
        "data_dir": str(DATA_DIR),
        "models_dir": str(MODELS_DIR),
        "dataset_dir": str(DATASET_DIR),
        "face_cosine_threshold": FACE_COSINE_THRESHOLD,
        "serpapi_key": redact(SERPAPI_KEY),
        "default_chain": DEFAULT_CHAIN,
        "rpc_url": RPC_URL,
        "sepolia_rpc_url": SEPOLIA_RPC_URL or "(unset)",
        "private_key": redact(PRIVATE_KEY),
        "solc_version": SOLC_VERSION,
    }
