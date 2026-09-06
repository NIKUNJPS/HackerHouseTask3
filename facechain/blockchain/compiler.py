"""Compile FaceRegistry.sol with py-solc-x (installs solc on first use)."""
from __future__ import annotations

import json
from pathlib import Path

import solcx

from .. import config, log

_CONTRACT = config.ROOT / "contracts" / "FaceRegistry.sol"
_ABI_CACHE = config.ARTIFACTS_DIR / "FaceRegistry.abi.json"
_BIN_CACHE = config.ARTIFACTS_DIR / "FaceRegistry.bin"


def _ensure_solc() -> None:
    versions = [str(v) for v in solcx.get_installed_solc_versions()]
    if config.SOLC_VERSION not in versions:
        log.info(f"installing solc {config.SOLC_VERSION} …")
        solcx.install_solc(config.SOLC_VERSION)


def compile_contract(force: bool = False) -> tuple[list, str]:
    """Return (abi, bytecode_hex). Cached under data/artifacts/."""
    if not force and _ABI_CACHE.exists() and _BIN_CACHE.exists():
        return json.loads(_ABI_CACHE.read_text()), _BIN_CACHE.read_text().strip()

    _ensure_solc()
    log.info(f"compiling {_CONTRACT.name} with solc {config.SOLC_VERSION} …")
    compiled = solcx.compile_files(
        [str(_CONTRACT)],
        output_values=["abi", "bin"],
        solc_version=config.SOLC_VERSION,
        optimize=True,
        optimize_runs=200,
    )
    key = next(k for k in compiled if k.endswith(":FaceRegistry"))
    iface = compiled[key]
    _ABI_CACHE.write_text(json.dumps(iface["abi"], indent=2))
    _BIN_CACHE.write_text(iface["bin"])
    log.ok("contract compiled")
    return iface["abi"], iface["bin"]
