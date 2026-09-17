"""Build the retry3 legacy sidecar transactionally after full validation."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import sod_gate_enforcer as sod


def build() -> tuple[Path, Path]:
    valid, message = sod._validate_retry2_sidecar(sod.load_canonical_gate_map())
    if not valid:
        raise RuntimeError(f"retry2 prevalidation failed: {message}")
    retry2_raw = sod.LEGACY_RECONCILIATION_RETRY2_FILE.read_bytes()
    payload = json.loads(retry2_raw.decode("utf-8"))
    records = payload["records"]
    if len(records) != 14 or set(records) != sod.LEGACY_DATE_KEYS:
        raise RuntimeError("retry2 does not contain the exact 14 records")
    output = {
        "version": sod.LEGACY_RECONCILIATION_RETRY3_VERSION,
        "supersedes": sod.LEGACY_RECONCILIATION_RETRY2_FILE.name,
        "supersedes_lock_sha256": sod.LEGACY_RECONCILIATION_RETRY2_LOCK.read_text(encoding="utf-8").strip(),
        "records": records,
    }
    raw = sod._canonical_json(output)
    lock = hashlib.sha256(raw).hexdigest().encode("ascii")
    target = sod.LEGACY_RECONCILIATION_RETRY3_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".retry3-", dir=target.parent) as temp_dir:
        temp = Path(temp_dir)
        sidecar = temp / target.name
        lock_file = temp / sod.LEGACY_RECONCILIATION_RETRY3_LOCK.name
        sidecar.write_bytes(raw)
        lock_file.write_bytes(lock)
        if json.loads(sidecar.read_bytes().decode("utf-8")) != output:
            raise RuntimeError("retry3 temp sidecar revalidation failed")
        if hashlib.sha256(sidecar.read_bytes()).hexdigest() != lock_file.read_text().strip():
            raise RuntimeError("retry3 temp lock revalidation failed")
        os.replace(sidecar, target)
        os.replace(lock_file, sod.LEGACY_RECONCILIATION_RETRY3_LOCK)
    valid, message = sod.resolve_active_legacy_sidecar()
    if not valid:
        raise RuntimeError(f"retry3 post-publish validation failed: {message}")
    return target, sod.LEGACY_RECONCILIATION_RETRY3_LOCK


if __name__ == "__main__":
    print("\n".join(str(path) for path in build()))
