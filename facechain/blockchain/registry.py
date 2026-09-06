"""High-level blockchain client: connect, deploy, anchor, read back, verify.

Supports three chain backends behind one interface:

* ``memory``  — in-process EVM (eth-tester). Zero setup; ideal for a self-contained
  demo. Accounts are pre-funded and unlocked.
* ``rpc``     — any JSON-RPC dev node (ganache / anvil / hardhat) at ``RPC_URL``.
  Transactions are signed locally with a private key (or a deterministic dev key
  derived from ``DEV_MNEMONIC``). Persists across processes.
* ``sepolia`` — the public Sepolia testnet at ``SEPOLIA_RPC_URL``. Real, public,
  persistent. Requires a funded key in ``PRIVATE_KEY``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from eth_account import Account
from web3 import Web3

from .. import config, log
from . import compiler


@dataclass
class ChainContext:
    w3: Web3
    address: str                 # sender / submitter address
    mode: str                    # "unlocked" | "key"
    name: str                    # memory | rpc | sepolia
    chain_id: int
    private_key: Optional[str] = None

    @property
    def explorer_tx(self):
        if self.name == "sepolia":
            return lambda h: f"https://sepolia.etherscan.io/tx/{h}"
        return lambda h: None


def _account_from_env_or_mnemonic(required: bool) -> tuple[str, str]:
    if config.PRIVATE_KEY:
        acct = Account.from_key(config.PRIVATE_KEY)
        return acct.address, config.PRIVATE_KEY
    if required:
        raise RuntimeError("PRIVATE_KEY is required for this chain. Set it in .env.")
    # derive deterministic dev account 0 (ganache/anvil/hardhat with DEV_MNEMONIC)
    Account.enable_unaudited_hdwallet_features()
    acct = Account.from_mnemonic(config.DEV_MNEMONIC)
    return acct.address, acct.key.hex()


def connect_chain(name: str = None) -> ChainContext:
    name = (name or config.DEFAULT_CHAIN).lower()

    if name == "memory":
        from web3 import EthereumTesterProvider
        w3 = Web3(EthereumTesterProvider())
        addr = w3.eth.accounts[0]
        return ChainContext(w3=w3, address=addr, mode="unlocked",
                            name="memory", chain_id=w3.eth.chain_id)

    if name in ("rpc", "ganache", "anvil", "local-node"):
        w3 = Web3(Web3.HTTPProvider(config.RPC_URL, request_kwargs={"timeout": 60}))
        if not w3.is_connected():
            raise RuntimeError(
                f"could not connect to JSON-RPC node at {config.RPC_URL}. "
                f"Start a local node, e.g.:\n"
                f'  npx ganache --wallet.mnemonic "{config.DEV_MNEMONIC}" '
                f"--miner.blockTime 0"
            )
        addr, key = _account_from_env_or_mnemonic(required=False)
        return ChainContext(w3=w3, address=addr, mode="key", name="rpc",
                            chain_id=w3.eth.chain_id, private_key=key)

    if name == "sepolia":
        if not config.SEPOLIA_RPC_URL:
            raise RuntimeError("SEPOLIA_RPC_URL is not set (e.g. an Alchemy/Infura URL).")
        w3 = Web3(Web3.HTTPProvider(config.SEPOLIA_RPC_URL, request_kwargs={"timeout": 60}))
        if not w3.is_connected():
            raise RuntimeError(f"could not connect to Sepolia at {config.SEPOLIA_RPC_URL}")
        addr, key = _account_from_env_or_mnemonic(required=True)
        return ChainContext(w3=w3, address=addr, mode="key", name="sepolia",
                            chain_id=w3.eth.chain_id, private_key=key)

    raise ValueError(f"unknown chain: {name!r} (use memory | rpc | sepolia)")


class FaceRegistry:
    """Deploy / attach the FaceRegistry contract and anchor + verify records."""

    def __init__(self, ctx: ChainContext, address: Optional[str] = None):
        self.ctx = ctx
        self.abi, self.bytecode = compiler.compile_contract()
        if address:
            self.address = Web3.to_checksum_address(address)
            self.contract = ctx.w3.eth.contract(address=self.address, abi=self.abi)
        else:
            self.address = None
            self.contract = None

    # -- tx plumbing ---------------------------------------------------------
    def _send(self, func) -> dict:
        ctx = self.ctx
        if ctx.mode == "unlocked":
            tx_hash = func.transact({"from": ctx.address})
        else:
            tx = func.build_transaction({
                "from": ctx.address,
                "nonce": ctx.w3.eth.get_transaction_count(ctx.address),
                "gasPrice": ctx.w3.eth.gas_price,
                "chainId": ctx.chain_id,
            })
            signed = ctx.w3.eth.account.sign_transaction(tx, ctx.private_key)
            raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
            tx_hash = ctx.w3.eth.send_raw_transaction(raw)
        rcpt = ctx.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        return {
            "tx_hash": rcpt.transactionHash.hex(),
            "block": rcpt.blockNumber,
            "gas_used": rcpt.gasUsed,
        }

    # -- deploy / attach -----------------------------------------------------
    def deploy(self) -> str:
        ctx = self.ctx
        factory = ctx.w3.eth.contract(abi=self.abi, bytecode=self.bytecode)
        if ctx.mode == "unlocked":
            tx_hash = factory.constructor().transact({"from": ctx.address})
        else:
            tx = factory.constructor().build_transaction({
                "from": ctx.address,
                "nonce": ctx.w3.eth.get_transaction_count(ctx.address),
                "gasPrice": ctx.w3.eth.gas_price,
                "chainId": ctx.chain_id,
            })
            signed = ctx.w3.eth.account.sign_transaction(tx, ctx.private_key)
            raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
            tx_hash = ctx.w3.eth.send_raw_transaction(raw)
        rcpt = ctx.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        self.address = rcpt.contractAddress
        self.contract = ctx.w3.eth.contract(address=self.address, abi=self.abi)
        self._save_deployment()
        return self.address

    def _save_deployment(self) -> None:
        p = config.DEPLOYMENTS_DIR / f"{self.ctx.name}.json"
        p.write_text(json.dumps({
            "network": self.ctx.name,
            "chain_id": self.ctx.chain_id,
            "address": self.address,
            "deployer": self.ctx.address,
        }, indent=2))

    @staticmethod
    def saved_address(network: str) -> Optional[str]:
        p = config.DEPLOYMENTS_DIR / f"{network}.json"
        if p.exists():
            return json.loads(p.read_text()).get("address")
        return None

    # -- anchor / read -------------------------------------------------------
    @staticmethod
    def _to_bytes32(fingerprint_hex: str) -> bytes:
        h = fingerprint_hex[2:] if fingerprint_hex.startswith("0x") else fingerprint_hex
        b = bytes.fromhex(h)
        if len(b) != 32:
            raise ValueError("fingerprint must be 32 bytes (keccak256)")
        return b

    def anchor(self, fingerprint_hex: str, uri: str) -> dict:
        fp = self._to_bytes32(fingerprint_hex)
        if self.contract.functions.exists(fp).call():
            log.warn("fingerprint already anchored on-chain; reading existing record")
            ts, submitter, on_uri = self.contract.functions.getRecord(fp).call()
            return {"tx_hash": None, "block": None, "gas_used": 0,
                    "already_anchored": True, "timestamp": ts,
                    "submitter": submitter, "uri": on_uri}
        receipt = self._send(self.contract.functions.anchor(fp, uri))
        ts, submitter, on_uri = self.contract.functions.getRecord(fp).call()
        receipt.update({"already_anchored": False, "timestamp": ts,
                        "submitter": submitter, "uri": on_uri})
        return receipt

    def read(self, fingerprint_hex: str) -> dict:
        fp = self._to_bytes32(fingerprint_hex)
        exists = self.contract.functions.exists(fp).call()
        ts, submitter, uri = self.contract.functions.getRecord(fp).call()
        return {"exists": exists, "timestamp": ts, "submitter": submitter, "uri": uri}

    def count(self) -> int:
        return self.contract.functions.recordCount().call()
