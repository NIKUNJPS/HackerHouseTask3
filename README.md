# FaceChain — Face Identification → Social Search → Blockchain Verification

An end‑to‑end pipeline that takes a **face scan**, finds a **matching post on the
web / social media**, and anchors a tamper‑evident **fingerprint of the discovery
on a blockchain** — then re‑verifies the data against the on‑chain record.

```
   ┌──────────────┐     ┌──────────────────────┐     ┌───────────────────────────┐
   │  Face scan   │ ──▶ │  Web / social search  │ ──▶ │  Blockchain anchor + verify │
   │ detect+embed │     │  reverse image / index │     │  keccak256 → on-chain proof │
   └──────────────┘     └──────────────────────┘     └───────────────────────────┘
```

Built for **HH Goa 2026 — Task 3**. No website; the focus is the working pipeline.

---

## What it actually does

1. **Face identification** — detects the face in an input image with OpenCV's
   **YuNet** detector and encodes it into a **128‑D embedding** with OpenCV's
   **SFace** recognizer. Same‑person photos score ~0.74 cosine, different people
   ~0.10, so this is real *identity* recognition, not image hashing.
2. **Social / web search** — a genuine search step, two interchangeable backends:
   * **Live web (SerpApi Google Lens):** publishes the image to a temporary host,
     runs a real reverse‑image search across the web, keeps hits on social‑media
     domains, and **face‑verifies** each candidate by re‑embedding its thumbnail.
   * **Offline index:** nearest‑neighbour search over a self‑built index of real
     social‑media images, each paired with its **real source URL**. Uses the same
     face embeddings, so an unknown face correctly returns *no match*.
3. **Blockchain verification** — builds a canonical record of the discovery
   (scanned‑face hash + matched post + score), hashes it to a 32‑byte
   **keccak256 fingerprint**, and anchors it in an append‑only Solidity contract
   (`FaceRegistry`). Re‑verification re‑reads the chain and recomputes the
   fingerprint; **any edit to the record breaks verification.**

---

## Quickstart (zero config, fully offline)

Everything below runs with **no API keys and no blockchain node** — the default
chain is an in‑process EVM.

```bash
# 1. install
pip install -r requirements.txt

# 2. fetch a small runnable demo dataset + a sample scan (public sample faces,
#    each paired with its real GitHub source URL)
python cli.py make-sample

# 3. build the offline face index
python cli.py build-index

# 4. run the full pipeline: face -> search -> anchor -> verify
python cli.py run --image samples/scan_person_a.jpg --provider local --chain memory
```

On first run the face models (~38 MB, OpenCV Zoo, pinned by sha256) and the solc
compiler are downloaded automatically.

Expected finish:

```
▸ STEP 5  Verify — re-read chain & recompute fingerprint
    off-chain integrity:         PASS
    on-chain fingerprint exists: PASS
    on-chain uri matches:        PASS
╔══════════════════════════════════════════════════════════════╗
║ ✅  VERIFIED ON-CHAIN                                         ║
╚══════════════════════════════════════════════════════════════╝
```

### Prove it's tamper‑evident

```bash
python cli.py verify --record data/records/record_XXXXXXXX.json --tamper match.url
```

Mutating a single field changes the recomputed fingerprint, so the ledger
rejects it → **🛡️ TAMPER‑EVIDENCE CONFIRMED**. That's the whole point of
anchoring on‑chain: an altered record can never pass verification.

---

## Real‑world live web search (SerpApi)

To search the *actual web/social media* instead of the offline index:

1. Get a free key at <https://serpapi.com> (100 searches/month).
2. `copy .env.example .env` and set `SERPAPI_KEY=...`
3. Run with the live backend:

```bash
python cli.py run --image path/to/your_selfie.jpg --provider serpapi --chain memory
```

The tool uploads the image to a temporary public host so Google Lens can fetch
it, gets real visual matches, filters to social‑media domains, and re‑embeds each
candidate thumbnail to confirm it's the same face.

> **Privacy:** the live path publishes your input image to a third‑party host
> (catbox.moe / 0x0.st). The offline path never uploads anything. Use images you
> are comfortable sharing, or stick to `--provider local`.

`--provider auto` (the default) picks `serpapi` when `SERPAPI_KEY` is set,
otherwise `local`.

---

## Blockchain options

| `--chain`  | What it is                              | Setup | Cross‑process verify |
|------------|-----------------------------------------|-------|----------------------|
| `memory`   | In‑process EVM (eth‑tester)             | none  | in‑run only (ephemeral) |
| `rpc`      | Local dev node (ganache / anvil / hardhat) | run a node | ✅ persistent |
| `sepolia`  | Public Sepolia testnet                  | RPC URL + funded key | ✅ public + persistent |

**Persistent local node (recommended for a separate `verify` step):**

```bash
# terminal A — start a persistent node with the default dev mnemonic
npx ganache --wallet.mnemonic "test test test test test test test test test test test junk" --miner.blockTime 0

# terminal B — anchor, then verify in a *separate* process against the live chain
python cli.py run    --image samples/scan_person_a.jpg --provider local --chain rpc
python cli.py verify --record data/records/record_XXXXXXXX.json
```

No key needed for the local node — the signer is derived from `DEV_MNEMONIC`
(matches ganache/anvil/hardhat's default account).

**Public Sepolia testnet** (real, public, persistent): set `SEPOLIA_RPC_URL`
(Alchemy/Infura) and a funded `PRIVATE_KEY` in `.env`, then use `--chain sepolia`.
The console prints a `https://sepolia.etherscan.io/tx/...` link for the anchor tx.

---

## The smart contract

[`contracts/FaceRegistry.sol`](contracts/FaceRegistry.sol) is an append‑only
registry: `anchor(fingerprint, uri)` stores `{timestamp, submitter, uri}` under a
fingerprint and **reverts if it already exists**, so a fingerprint maps to exactly
one immutable record. `getRecord` / `exists` / `recordCount` read it back for
verification and audit.

### What gets fingerprinted

`keccak256` over a canonical (sorted, compact) JSON:

```json
{
  "schema": "facechain/fingerprint/v1",
  "created_at": "2026-09-06T...Z",
  "query":  { "image_sha256": "...", "face_embedding_sha256": "..." },
  "match":  { "provider": "local", "platform": "github", "url": "...",
              "image_sha256": "...", "match_score": 0.7437, "face_verified": true }
}
```

The full record (including the base64 face embedding and the chain coordinates —
network, contract address, tx hash, block) is saved to `data/records/*.json`.

---

## Repository layout

```
contracts/FaceRegistry.sol      Solidity append-only registry
facechain/
  face/        recognizer.py     YuNet detect + SFace 128-D embeddings
               models.py         download + sha256-verify the ONNX models
  search/      serpapi_provider  live reverse-image search (Google Lens)
               local_index       offline face-embedding index
               uploader.py       temp public image host for the live path
  blockchain/  compiler.py       solc compile (py-solc-x)
               registry.py       connect / deploy / anchor / read (memory|rpc|sepolia)
  fingerprint.py                 canonical record + keccak256
  pipeline.py                    the end-to-end orchestrator
cli.py                           run | verify | build-index | make-sample | info
scripts/make_sample_dataset.py   downloads the runnable demo data
tests/                           offline smoke tests (contract + fingerprint)
```

---

## CLI reference

```
python cli.py run  --image IMG [--provider auto|serpapi|local]
                               [--chain memory|rpc|sepolia] [--redeploy]
                               [--allow-unverified] [--json]
python cli.py verify --record data/records/REC.json [--tamper match.url] [--json]
python cli.py build-index [--dataset dataset]
python cli.py make-sample
python cli.py info
```

---

## Using your own data (offline index)

Drop social‑media images into `dataset/` and add `dataset/sources.json` mapping
each file to its real post URL (see [`dataset/README.md`](dataset/README.md)),
then `python cli.py build-index`. Scan a *different* photo of yourself and the
pipeline will find your post by face similarity.

---

## Tests

Offline smoke tests (no models/network — just the chain + fingerprint logic):

```bash
pip install pytest
pytest -q
```

CI runs them on every push (`.github/workflows/ci.yml`).

---

## One‑command demo (for the screen recording)

After `pip install -r requirements.txt`, the entire narrative runs in a single
clean take (no filenames to copy on camera):

```bash
python demo.py                          # one image, then the tamper-evidence test
python demo.py --pause                  # waits for Enter between steps, for narration
python demo.py img1.jpg img2.jpg ...    # run several images back to back
python demo.py --no-tamper              # skip the tamper step
```

With `SERPAPI_KEY` set, the demo runs the **live web search** and prints every
social‑media post it finds (Instagram, Facebook, X, …), ranked by face
similarity; otherwise it uses the offline index. Both are genuine searches.

## Screen‑recording checklist

Prefer `python demo.py` (add a few image paths for a multi‑face take). It shows,
end to end:

1. **Face scan** — face detected, box + score, 128‑D embedding.
2. **Social/web search** — the ranked list of real posts found on the live web,
   then the chosen **post URL** (a real Instagram/Facebook/X link).
3. **Blockchain** — fingerprint, **tx hash + block**, **✅ VERIFIED ON-CHAIN**.
4. **Tamper‑evidence** — one field is edited → **🛡️ TAMPER‑EVIDENCE CONFIRMED**
   (the altered record is rejected).

Optional extras: `--chain rpc` with `npx ganache …` for a persistent local chain
and cross‑process `verify`; `--chain sepolia` for a public Etherscan link.

---

## Which blockchain did we use?

* Default demo: an **in‑process EVM** (eth‑tester / Py‑EVM) — a local/simulated
  chain, zero setup.
* Persistent local: **ganache / anvil / hardhat** over JSON‑RPC (`--chain rpc`).
* Real public network: **Ethereum Sepolia testnet** (`--chain sepolia`).

The exact same Solidity contract and verification path run on all three.

## Known limitations

* **Face‑search engines are paid.** Dedicated face search (PimEyes, FaceCheck)
  needs paid APIs. We use SerpApi **Google Lens reverse‑image** (finds pages
  containing the image) plus thumbnail face‑verification for the live path, and a
  real **face‑embedding index** for the offline path. Both are genuine searches.
* **Live search coverage** depends on what Google Lens indexes for that image;
  some faces return no social‑domain hits.
* **`memory` chain is ephemeral** — use `rpc` or `sepolia` for cross‑process /
  long‑lived proofs.
* **Recognition** uses SFace (good, lightweight). Extreme pose/lighting/occlusion
  lowers accuracy; tune `FACECHAIN_FACE_THRESHOLD` if needed.
* **Demo data** are public sample faces; for real use, supply your own images and
  source URLs, or use the live SerpApi path.

## Tech stack

OpenCV (YuNet + SFace) · web3.py · py‑solc‑x / Solidity 0.8 · eth‑tester / Py‑EVM ·
SerpApi (Google Lens) · Python 3.11.

## License

MIT — see [LICENSE](LICENSE).
