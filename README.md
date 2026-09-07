<div align="center">

# FaceChain

### Face Identification → Social/Web Search → Blockchain Verification

A production-style pipeline that takes a **face scan**, finds a **real matching post on the web / social media**, and anchors a **tamper-evident fingerprint** of that discovery on a **blockchain** — then re-verifies the data against the on-chain record.

[![CI](https://github.com/NIKUNJPS/HackerHouseTask3/actions/workflows/ci.yml/badge.svg)](https://github.com/NIKUNJPS/HackerHouseTask3/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Blockchain](https://img.shields.io/badge/chain-EVM%20%7C%20Sepolia-purple)

</div>

```
   ┌──────────────┐      ┌────────────────────────┐      ┌────────────────────────────┐
   │  Face scan   │  ──▶ │  Web / social search    │  ──▶ │  Blockchain anchor + verify │
   │ detect+embed │      │  reverse image / index  │      │  keccak256 → on-chain proof │
   └──────────────┘      └────────────────────────┘      └────────────────────────────┘
```

---

## Table of contents

- [Overview](#overview)
- [How it works](#how-it-works)
- [Tech stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Running the demo](#running-the-demo)
- [CLI reference](#cli-reference)
- [Search backends](#search-backends)
- [Blockchain backends](#blockchain-backends)
- [How verification & tamper-evidence work](#how-verification--tamper-evidence-work)
- [Project structure](#project-structure)
- [Configuration](#configuration)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Known limitations](#known-limitations)
- [License](#license)

---

## Overview

FaceChain implements a complete, verifiable identity pipeline:

1. **Face identification** — detect a face in an input image and encode it into a 128-dimensional embedding.
2. **Social / web search** — use that face to search the web and return at least one **real, matching social-media post**. This is a genuine search step (live reverse-image search or a face-embedding index), never a hard-coded result.
3. **Blockchain verification** — hash the discovery into a fingerprint and anchor it in an append-only smart contract, creating a **tamper-evident** record that can be independently re-verified.

No website or hosting is required — everything runs from the command line.

## How it works

| Stage | What happens | Implementation |
|-------|--------------|----------------|
| **1. Face** | Detect the most prominent face, align it, and produce a 128-D embedding. Same person across different photos scores ~0.74 cosine; different people ~0.10. | OpenCV **YuNet** (detector) + **SFace** (recognizer) |
| **2. Search** | Turn the face into a real matching post. Two interchangeable backends (see [below](#search-backends)). Live results are **face-verified** by re-embedding each candidate's image. | SerpApi **Google Lens** / offline **face-embedding index** |
| **3. Blockchain** | Build a canonical record (scanned-face hash + matched post + score), hash it to a **keccak256** fingerprint, and anchor it on-chain. Re-verification re-reads the chain and recomputes the fingerprint. | **Solidity** `FaceRegistry` via **web3.py** on an EVM chain |

## Tech stack

- **Face:** OpenCV (`FaceDetectorYN` + `FaceRecognizerSF`) — no dlib, no heavyweight ML framework.
- **Search:** SerpApi Google Lens (live reverse-image search) + a local NumPy face-embedding index.
- **Blockchain:** Solidity 0.8, `web3.py`, `py-solc-x` (compiler), `eth-tester` / `py-evm` (in-process EVM), with support for ganache/anvil and the Ethereum Sepolia testnet.
- **Language:** Python 3.11.

## Prerequisites

- **Python 3.11+**
- **Git**
- Internet access on first run (downloads the face models, ~38 MB, and the Solidity compiler)
- *(optional)* A free [SerpApi](https://serpapi.com) key for live web search
- *(optional)* Node.js if you want a persistent local chain via `npx ganache`

## Quick start

For a teammate cloning the repo for the first time:

```bash
# 1. clone
git clone https://github.com/NIKUNJPS/HackerHouseTask3.git
cd HackerHouseTask3

# 2. create and activate a virtual environment
python -m venv .venv
# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
# macOS / Linux
# source .venv/bin/activate

# 3. install dependencies
pip install -r requirements.txt

# 4. run the full pipeline end-to-end
python demo.py
```

That's it. The first run downloads the face models and compiler automatically, prepares a sample input, runs face → search → blockchain → verify, and finishes with a tamper-evidence test.

> **PowerShell tip:** if activation is blocked by execution policy, either run
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first, or skip
> activation and call the venv Python directly: `.\.venv\Scripts\python.exe demo.py`.

### Enabling live web search (recommended)

By default the demo uses the offline face index. To search the **live web** and return real Instagram/Facebook/X posts:

```bash
# copy the env template and add your key
copy .env.example .env        # Windows   (use: cp .env.example .env  on macOS/Linux)
```

Edit `.env` and set:

```
SERPAPI_KEY=your_key_here
```

Now `python demo.py` automatically uses the live search.

## Running the demo

```bash
python demo.py                          # one image + tamper-evidence test
python demo.py --pause                  # pause between steps (ideal for narration/recording)
python demo.py img1.jpg img2.jpg ...    # run several faces back to back
python demo.py --no-tamper              # skip the tamper-evidence step
```

Example — a two-face run using the bundled samples:

```bash
python demo.py samples/scan_person_a.jpg samples/scan_person_b.jpg --pause
```

You'll see, per image: the face detected, the ranked list of **real social-media posts found on the live web** (Instagram, Facebook, X, …), the chosen match, the on-chain **transaction hash**, and **✅ VERIFIED ON-CHAIN** — followed by **🛡️ TAMPER-EVIDENCE CONFIRMED**.

## CLI reference

The demo wraps `cli.py`, which you can also drive directly:

```bash
# full pipeline on one image
python cli.py run --image <path> [--provider auto|serpapi|local] [--chain memory|rpc|sepolia] [--json]

# re-verify a saved record against the chain
python cli.py verify --record data/records/<file>.json [--tamper match.url]

# offline index management
python cli.py build-index [--dataset dataset]
python cli.py make-sample          # download a runnable sample dataset + input

# show current configuration
python cli.py info
```

## Search backends

Both backends are genuine searches (they can return "no match"); neither hard-codes a result.

| Backend | Flag | What it does | Needs |
|---------|------|--------------|-------|
| **Live web** | `--provider serpapi` | Publishes the image to a temporary host, runs a real Google Lens reverse-image search, filters to social-media domains, and **face-verifies** each candidate by re-embedding its image. Prints every match ranked by similarity. | `SERPAPI_KEY` |
| **Offline index** | `--provider local` | Nearest-neighbour search over a self-built index of real social-media images, each paired with its real source URL. Uses the same embeddings, so an unknown face returns *no match*. | a built index |
| **Auto** | `--provider auto` (default) | Uses `serpapi` when a key is set, otherwise `local`. | — |

To use your own data with the offline index, drop images into `dataset/` with a `dataset/sources.json` mapping each file to its real post URL (see [`dataset/README.md`](dataset/README.md)), then `python cli.py build-index`.

## Blockchain backends

| `--chain` | Description | Setup | Cross-process verify |
|-----------|-------------|-------|----------------------|
| `memory` *(default)* | In-process EVM (`eth-tester`) | none | in-run only (ephemeral) |
| `rpc` | Local dev node (ganache / anvil / hardhat) at `RPC_URL` | run a node | ✅ persistent |
| `sepolia` | Public Ethereum Sepolia testnet at `SEPOLIA_RPC_URL` | RPC URL + funded key | ✅ public + persistent |

**Persistent local chain** (lets `verify` run as a separate process):

```bash
# terminal A
npx ganache --wallet.mnemonic "test test test test test test test test test test test junk" --miner.blockTime 0

# terminal B
python cli.py run    --image samples/scan_person_a.jpg --chain rpc
python cli.py verify --record data/records/<file>.json
```

**Public Sepolia testnet:** set `SEPOLIA_RPC_URL` (Alchemy/Infura) and a funded `PRIVATE_KEY` in `.env`, then use `--chain sepolia`. The console prints a `https://sepolia.etherscan.io/tx/...` link for each anchor.

## How verification & tamper-evidence work

The **fingerprint** is `keccak256` over a canonical (sorted, compact) JSON of the discovery:

```json
{
  "schema": "facechain/fingerprint/v1",
  "created_at": "2026-09-07T...Z",
  "query":  { "image_sha256": "...", "face_embedding_sha256": "..." },
  "match":  { "provider": "serpapi", "platform": "instagram", "url": "...",
              "image_sha256": "...", "match_score": 0.83, "face_verified": true }
}
```

That 32-byte value is anchored in the [`FaceRegistry`](contracts/FaceRegistry.sol) contract (append-only: a fingerprint maps to exactly one immutable record). Verification recomputes the fingerprint from the saved record and checks it against the ledger. Because changing **any** field changes the hash, an edited record can never pass:

```bash
python cli.py verify --record data/records/<file>.json --tamper match.url
# → 🛡️ TAMPER-EVIDENCE CONFIRMED (the altered record is rejected)
```

Each full record — including the face embedding and chain coordinates (network, contract, tx hash, block) — is saved under `data/records/`.

## Project structure

```
contracts/FaceRegistry.sol       Append-only Solidity registry
facechain/
  face/        recognizer.py      YuNet detect + SFace 128-D embeddings
               models.py          download + sha256-verify the ONNX models
  search/      serpapi_provider   live Google Lens reverse-image search
               local_index        offline face-embedding index
               uploader.py        temp public image host (live path only)
  blockchain/  compiler.py        Solidity compilation (py-solc-x)
               registry.py        connect / deploy / anchor / read (memory|rpc|sepolia)
  fingerprint.py                  canonical record + keccak256
  pipeline.py                     end-to-end orchestrator
cli.py                            run | verify | build-index | make-sample | info
demo.py                           one-command, recording-friendly walkthrough
scripts/make_sample_dataset.py    downloads the runnable sample data
tests/                            offline smoke tests (contract + fingerprint)
```

## Configuration

All settings are optional (defaults work out of the box). Set them via environment variables or a `.env` file — see [`.env.example`](.env.example).

| Variable | Default | Purpose |
|----------|---------|---------|
| `SERPAPI_KEY` | — | Enables live web search |
| `FACECHAIN_CHAIN` | `memory` | Default chain (`memory` / `rpc` / `sepolia`) |
| `RPC_URL` | `http://127.0.0.1:8545` | Local dev node for `--chain rpc` |
| `SEPOLIA_RPC_URL` | — | Sepolia endpoint for `--chain sepolia` |
| `PRIVATE_KEY` | — | Signer for remote chains (never commit a real key) |
| `FACECHAIN_FACE_THRESHOLD` | `0.363` | Cosine threshold for a same-identity match |

## Testing

Offline smoke tests (no models or network required — just the chain + fingerprint logic):

```bash
pip install pytest
pytest -q
```

Continuous integration runs these on every push via [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Troubleshooting

- **First run is slow / downloads a lot** — it fetches the face models (~38 MB) and the Solidity compiler once, then caches them.
- **`SERPAPI_KEY is not set`** — add it to `.env`, or run with `--provider local`.
- **Live search returns no social match** — depends on what Google Lens indexes for that image; try a different, widely-posted photo, or the offline index.
- **`could not connect to JSON-RPC node`** — start a local node first (see [Blockchain backends](#blockchain-backends)) before using `--chain rpc`.
- **Garbled box characters on Windows** — use Windows Terminal (UTF-8); the app also falls back to ASCII automatically.

## Known limitations

- Dedicated face-search engines (PimEyes, FaceCheck) are paid; we use Google Lens reverse-image search plus thumbnail face-verification for the live path, and a real face-embedding index for the offline path. Both are genuine searches.
- Live-search coverage depends on what the search engine has indexed for a given image.
- The `memory` chain is ephemeral; use `rpc` or `sepolia` for cross-process, long-lived proofs.
- The live path uploads the input image to a temporary public host so Google Lens can fetch it; the offline path never uploads anything.
- Recognition uses SFace (lightweight, accurate for frontal faces); extreme pose/lighting/occlusion lowers accuracy — tune `FACECHAIN_FACE_THRESHOLD` if needed.

## License

Released under the [MIT License](LICENSE).
