"""Unit tests for Hybrid Sharded JSON + SQLite Cache Store (scripts/gate_store.py)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from scripts import gate_store, update_gate
from pathlib import Path

import pytest

from scripts.gate_store import GateStore, GateStoreLock


@pytest.fixture
def temp_gate_store(tmp_path: Path) -> GateStore:
    gates_dir = tmp_path / "gates"
    db_path = tmp_path / "phase_gates.db"
    legacy_json = tmp_path / "phase_gates.json"

    # Pre-populate dummy legacy JSON
    sample_data = {
        "GATE_ALPHA_20261001": {
            "phase_name": "GATE_ALPHA_20261001",
            "final_verdict": "[APPROVED]",
            "timestamp": "2026-10-01T00:00:00+07:00",
            "l2_session_id": "l2_role9_alpha",
            "l2_role_id": 9,
            "l2_role_name": "backend-engineer",
            "l3_session_id": "l3_role21_alpha",
            "l3_role_id": 21,
            "l3_role_name": "code-reviewer",
            "audit_report_path": ".ly_state/session/audit_reports/role21_alpha.md",
            "sod_boundary_checked": True,
            "writer_auditor_separated": True,
            "l2_completed": True,
        },
        "GATE_BETA_20261002": {
            "phase_name": "GATE_BETA_20261002",
            "final_verdict": "[NEEDS_FIX]",
            "timestamp": "2026-10-02T00:00:00+07:00",
            "l2_session_id": "l2_role15_beta",
            "l2_role_id": 15,
            "l2_role_name": "data-engineer",
            "l3_session_id": "l3_role21_beta",
            "l3_role_id": 21,
            "l3_role_name": "code-reviewer",
            "audit_report_path": ".ly_state/session/audit_reports/role21_beta.md",
            "sod_boundary_checked": True,
            "writer_auditor_separated": True,
            "l2_completed": True,
        },
    }
    legacy_json.write_text(json.dumps(sample_data, indent=2), encoding="utf-8")
    return GateStore(gates_dir=gates_dir, db_path=db_path, legacy_json_path=legacy_json)


def test_bootstrap_from_legacy_json(temp_gate_store: GateStore):
    count = temp_gate_store.bootstrap_from_legacy_json()
    assert count == 2

    shard_alpha = temp_gate_store.gates_dir / "GATE_ALPHA_20261001.json"
    shard_beta = temp_gate_store.gates_dir / "GATE_BETA_20261002.json"
    assert shard_alpha.is_file()
    assert shard_beta.is_file()

    alpha_data = json.loads(shard_alpha.read_text(encoding="utf-8"))
    assert alpha_data["final_verdict"] == "[APPROVED]"
    assert alpha_data["l2_role_id"] == 9


def test_sqlite_cache_auto_sync_and_query(temp_gate_store: GateStore):
    temp_gate_store.bootstrap_from_legacy_json()
    synced = temp_gate_store.sync_cache()
    assert synced == 2
    assert temp_gate_store.db_path.is_file()

    # Query single gate
    gate = temp_gate_store.get_gate("GATE_ALPHA_20261001")
    assert gate is not None
    assert gate["phase_name"] == "GATE_ALPHA_20261001"
    assert gate["final_verdict"] == "[APPROVED]"

    # Filter gates
    approved = temp_gate_store.filter_gates("[APPROVED]")
    assert len(approved) == 1
    assert approved[0]["phase_name"] == "GATE_ALPHA_20261001"

    needs_fix = temp_gate_store.filter_gates("[NEEDS_FIX]")
    assert len(needs_fix) == 1
    assert needs_fix[0]["phase_name"] == "GATE_BETA_20261002"


def test_save_gate_persists_shard_and_updates_cache(temp_gate_store: GateStore):
    temp_gate_store.bootstrap_from_legacy_json()
    temp_gate_store.sync_cache()

    new_gate = {
        "phase_name": "GATE_GAMMA_20261003",
        "final_verdict": "[APPROVED]",
        "timestamp": "2026-10-03T00:00:00+07:00",
        "l2_session_id": "l2_role9_gamma",
        "l2_role_id": 9,
        "l2_role_name": "backend-engineer",
        "l3_session_id": "l3_role21_gamma",
        "l3_role_id": 21,
        "l3_role_name": "code-reviewer",
        "audit_report_path": ".ly_state/session/audit_reports/role21_gamma.md",
        "sod_boundary_checked": True,
        "writer_auditor_separated": True,
        "l2_completed": True,
    }

    shard_path = temp_gate_store.save_gate("GATE_GAMMA_20261003", new_gate)
    assert shard_path.is_file()

    # Verify query cache immediately reflects new gate
    retrieved = temp_gate_store.get_gate("GATE_GAMMA_20261003")
    assert retrieved is not None
    assert retrieved["phase_name"] == "GATE_GAMMA_20261003"
    assert retrieved["final_verdict"] == "[APPROVED]"

    # Verify legacy JSON is updated
    legacy_all = json.loads(temp_gate_store.legacy_json_path.read_text(encoding="utf-8"))
    assert "GATE_GAMMA_20261003" in legacy_all
    assert len(legacy_all) == 3


def test_mtime_invalidation_and_disk_rebuild(temp_gate_store: GateStore):
    temp_gate_store.bootstrap_from_legacy_json()
    temp_gate_store.sync_cache()

    # Manually modify a shard on disk (simulating git pull or manual edit)
    shard_alpha = temp_gate_store.gates_dir / "GATE_ALPHA_20261001.json"
    alpha_data = json.loads(shard_alpha.read_text(encoding="utf-8"))
    alpha_data["final_verdict"] = "[APPROVED_MODIFIED]"
    shard_alpha.write_text(json.dumps(alpha_data, indent=2), encoding="utf-8")

    # Ensure mtime changes
    now = time.time() + 1.0
    import os
    os.utime(shard_alpha, (now, now))

    # Next get_gate should detect mtime drift and re-sync
    retrieved = temp_gate_store.get_gate("GATE_ALPHA_20261001")
    assert retrieved is not None
    assert retrieved["final_verdict"] == "[APPROVED_MODIFIED]"


def test_delete_gate(temp_gate_store: GateStore):
    temp_gate_store.bootstrap_from_legacy_json()
    temp_gate_store.sync_cache()

    assert temp_gate_store.get_gate("GATE_BETA_20261002") is not None
    deleted = temp_gate_store.delete_gate("GATE_BETA_20261002")
    assert deleted is True

    assert temp_gate_store.get_gate("GATE_BETA_20261002") is None
    shard_beta = temp_gate_store.gates_dir / "GATE_BETA_20261002.json"
    assert not shard_beta.exists()

    legacy_all = json.loads(temp_gate_store.legacy_json_path.read_text(encoding="utf-8"))
    assert "GATE_BETA_20261002" not in legacy_all


def test_gate_store_lock_concurrency(tmp_path: Path):
    lock_file = tmp_path / "test.lock"
    with GateStoreLock(lock_path=lock_file, timeout_sec=1.0) as lock1:
        assert lock_file.exists()
        # Second lock attempt should timeout
        with pytest.raises(RuntimeError, match="lock timeout"):
            with GateStoreLock(lock_path=lock_file, timeout_sec=0.1):
                pass
    assert lock_file.is_file()  # Persistent inode prevents split-lock races.
    with GateStoreLock(lock_file, timeout_sec=0):
        pass


@pytest.mark.parametrize("name", [None, "", [], 123, "../escape", "/absolute", "--flag", "a/b", "x" * 129],
                         ids=["none", "empty", "list", "number", "traversal", "absolute", "flag", "slash", "long"])
@pytest.mark.parametrize("operation", ["get", "save", "delete"])
def test_identifier_validation_symmetry(temp_gate_store, name, operation):
    with pytest.raises(ValueError, match="identifier"):
        if operation == "save":
            temp_gate_store.save_gate(name, {})
        else:
            getattr(temp_gate_store, operation + "_gate")(name)
    assert not list(temp_gate_store.gates_dir.glob("*.json"))


@pytest.mark.parametrize("record", [None, [], "", {"phase_name": "OTHER"},
    {"l2_role_id": True}, {"l2_role_id": 2**64}, {"l2_role_id": -1},
    {"final_verdict": []}, {"l2_completed": "false"},
    {"repo_local_skill_sources": [1]}, {1: "bad"},
    {"x": float("nan")}, {"x": float("inf")}, {"x": -float("inf")}])
def test_record_validation_before_mutation(temp_gate_store, record):
    before = temp_gate_store.legacy_json_path.read_bytes()
    with pytest.raises(ValueError):
        temp_gate_store.save_gate("GATE", record)
    assert temp_gate_store.legacy_json_path.read_bytes() == before
    assert not list(temp_gate_store.gates_dir.glob("*.json"))


@pytest.mark.parametrize("raw", [b'[]', b'{', b'{"phase_name":"OTHER"}',
    b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}', b'\xff', b'\xef\xbb\xbf{}'])
def test_corrupt_shards_fail_closed(temp_gate_store, raw):
    temp_gate_store.bootstrap_from_legacy_json()
    temp_gate_store.sync_cache()
    shard = temp_gate_store.gates_dir / "GATE_ALPHA_20261001.json"
    shard.write_bytes(raw)
    before = temp_gate_store.legacy_json_path.read_bytes()
    for operation in (temp_gate_store.list_gates, temp_gate_store.filter_gates,
                      lambda: temp_gate_store.save_gate("NEW", {}),
                      lambda: temp_gate_store.delete_gate("GATE_BETA_20261002")):
        with pytest.raises(ValueError):
            operation()
    assert temp_gate_store.legacy_json_path.read_bytes() == before
    assert not (temp_gate_store.gates_dir / "NEW.json").exists()


def test_cache_handles_deletions_same_mtime_and_backdated_additions(temp_gate_store):
    store = temp_gate_store
    store.bootstrap_from_legacy_json()
    store.sync_cache()
    alpha = store._shard_path("GATE_ALPHA_20261001")
    stamp = alpha.stat().st_mtime_ns
    data = json.loads(alpha.read_bytes())
    data["final_verdict"] = "CHANGED"
    alpha.write_bytes(json.dumps(data).encode())
    os.utime(alpha, ns=(stamp, stamp))
    store._shard_path("GATE_BETA_20261002").unlink()
    new = store._shard_path("OLD")
    new.write_bytes(b'{"phase_name":"OLD"}')
    os.utime(new, ns=(1, 1))
    assert store.get_gate("GATE_ALPHA_20261001")["final_verdict"] == "CHANGED"
    assert set(store.list_gates()) == {"GATE_ALPHA_20261001", "OLD"}
    for path in store.gates_dir.glob("*.json"):
        path.unlink()
    assert store.list_gates() == {}
    assert store.bootstrap_from_legacy_json() == 0


def test_bootstrap_never_overwrites_or_resurrects(temp_gate_store):
    store = temp_gate_store
    store.bootstrap_from_legacy_json()
    assert store.bootstrap_from_legacy_json() == 0
    store.delete_gate("GATE_ALPHA_20261001", sync_legacy=False)
    store.delete_gate("GATE_BETA_20261002", sync_legacy=False)
    assert store.list_gates() == {}
    assert store.bootstrap_from_legacy_json() == 0


@pytest.mark.parametrize("raw", [b'[]', b'{"GATE":[]}', b'{"GATE":{},"GATE":{}}',
    b'{"GOOD":{},"../BAD":{}}', b'{"GATE":{"x":Infinity}}', b'\xef\xbb\xbf{}'])
def test_bootstrap_validates_entire_snapshot(temp_gate_store, raw):
    store = temp_gate_store
    store.legacy_json_path.write_bytes(raw)
    with pytest.raises(ValueError):
        store.bootstrap_from_legacy_json()
    assert not list(store.gates_dir.glob("*.json"))
    assert not store.journal_path.exists()


@pytest.mark.parametrize("failure_target", ["shard", "facade", "marker", "journal_cleanup"])
@pytest.mark.parametrize("operation", ["save", "delete", "bootstrap"])
def test_publication_replays_after_fault(temp_gate_store, monkeypatch, failure_target, operation):
    store = temp_gate_store
    if operation != "bootstrap":
        store.bootstrap_from_legacy_json()
    real_write = gate_store._atomic_write_bytes
    real_unlink = Path.unlink
    target = {"shard": store._shard_path("GATE_ALPHA_20261001"),
              "facade": store.legacy_json_path, "marker": store.marker_path}.get(failure_target)
    fired = False

    def injected_write(path, raw):
        nonlocal fired
        if path == target and not fired:
            fired = True
            raise OSError("injected publication failure")
        return real_write(path, raw)

    def injected_unlink(path, *args, **kwargs):
        nonlocal fired
        if not fired and ((failure_target == "journal_cleanup" and path == store.journal_path)
                          or (failure_target == "shard" and operation == "delete" and path == target)):
            fired = True
            raise OSError("injected unlink failure")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(gate_store, "_atomic_write_bytes", injected_write)
    monkeypatch.setattr(Path, "unlink", injected_unlink)
    with pytest.raises(RuntimeError, match="committed; recovery required"):
        if operation == "bootstrap":
            store.bootstrap_from_legacy_json()
        elif operation == "save":
            store.save_gate("GATE_ALPHA_20261001", {"note": "new"})
        else:
            store.delete_gate("GATE_ALPHA_20261001")
    assert fired and store.journal_path.is_file()
    recovered = GateStore(store.gates_dir, store.db_path, store.legacy_json_path).list_gates()
    if operation == "save":
        assert recovered["GATE_ALPHA_20261001"]["note"] == "new"
    elif operation == "delete":
        assert "GATE_ALPHA_20261001" not in recovered
    else:
        assert len(recovered) == 2
    assert json.loads(store.legacy_json_path.read_bytes()) == recovered
    assert not store.journal_path.exists()


@pytest.mark.parametrize("stage", ["fsync", "replace"], ids=["fsync", "atomic_replace"])
def test_precommit_failure_preserves_snapshot(temp_gate_store, monkeypatch, stage):
    store = temp_gate_store
    store.bootstrap_from_legacy_json()
    before = {p: p.read_bytes() for p in store.gates_dir.glob("*.json")}
    legacy = store.legacy_json_path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(gate_store.os, stage, lambda *args: (_ for _ in ()).throw(OSError("fault")))
        with pytest.raises(OSError):
            store.save_gate("NEW", {})
    assert {p: p.read_bytes() for p in store.gates_dir.glob("*.json")} == before
    assert store.legacy_json_path.read_bytes() == legacy
    assert not store.journal_path.exists()
    assert not list(store.gates_dir.parent.rglob("*.tmp"))


def test_cache_corruption_rebuild_and_failure_does_not_rollback(temp_gate_store, monkeypatch):
    store = temp_gate_store
    store.bootstrap_from_legacy_json()
    store.db_path.write_bytes(b"not sqlite")
    assert len(store.list_gates()) == 2
    with monkeypatch.context() as patch:
        patch.setattr(store, "_sync_cache", lambda *args: (_ for _ in ()).throw(RuntimeError("cache fault")))
        with pytest.raises(RuntimeError, match="cache fault"):
            store.save_gate("NEW", {"note": "committed"})
    assert store.get_gate("NEW")["note"] == "committed"
    assert "NEW" in json.loads(store.legacy_json_path.read_bytes())


@pytest.mark.parametrize("target", ["shard", "legacy", "db", "journal", "marker", "lock"])
def test_directory_in_file_position_rejected(temp_gate_store, target):
    store = temp_gate_store
    paths = {"shard": store._shard_path("GATE"), "legacy": store.legacy_json_path,
             "db": store.db_path, "journal": store.journal_path,
             "marker": store.marker_path, "lock": store.lock_path}
    path = paths[target]
    if path.exists():
        path.unlink()
    path.mkdir()
    with pytest.raises((ValueError, OSError)):
        store.save_gate("GATE", {})


def test_lock_age_never_steals_and_worker_crash_releases(tmp_path):
    path = tmp_path / "process.lock"
    with GateStoreLock(path):
        os.utime(path, (1, 1))
        with pytest.raises(RuntimeError, match="lock timeout"):
            with GateStoreLock(path, timeout_sec=0):
                pass
    code = "from pathlib import Path; from scripts.gate_store import GateStoreLock; import os,sys; lock=GateStoreLock(Path(sys.argv[1])); lock.__enter__(); os._exit(0)"
    result = subprocess.run([sys.executable, "-c", code, str(path)], cwd=Path(__file__).resolve().parents[1], timeout=15)
    assert result.returncode == 0
    with GateStoreLock(path, timeout_sec=0):
        pass


def test_concurrent_writers_and_updater_preserve_sparse_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Updater's session layout is intentionally isolated from the repository.
    session = Path.cwd() / ".ly_state/session"
    session.mkdir(parents=True, exist_ok=True)
    session.joinpath("phase_gates.json").write_bytes(b'{"GATE":{"phase_name":"GATE","keep":1},"OTHER":{"x":2}}')
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda n: update_gate._update_gate("GATE", {f"field{n}": n}), range(8)))
    hybrid = GateStore(session / "gates", session / "phase_gates.db", session / "phase_gates.json")
    result = hybrid.list_gates()
    assert result["GATE"]["keep"] == 1
    assert all(result["GATE"][f"field{n}"] == n for n in range(8))
    assert result["OTHER"]["x"] == 2


def test_unicode_crlf_and_opaque_domain_values_roundtrip(temp_gate_store):
    store = temp_gate_store
    record = {"note": "Tiếng Việt", "price": 1_000_000_000_001,
              "zero": 0, "negative": -1, "session_close": "2026-10-15T15:30:00+07:00"}
    original = dict(record)
    store.save_gate("GATE", record)
    assert record == original
    shard = store._shard_path("GATE")
    shard.write_bytes(shard.read_bytes().replace(b"\n", b"\r\n"))
    assert store.get_gate("GATE") == {**record, "phase_name": "GATE"}
    store.export_monolithic_json()
    assert b"\r" not in store.legacy_json_path.read_bytes()


@pytest.mark.parametrize("reserved", ["phase_gates.db", "phase_gates.db-wal", "phase_gates.db-shm",
    "phase_gates.db-journal", "gate_store.lock", "gate_store.pending.json", "gate_close.lock"])
@pytest.mark.parametrize("variant", ["upper", "mixed", "dot", "space", "stream"])
def test_export_rejects_reserved_aliases_without_recovery(temp_gate_store, monkeypatch, reserved, variant):
    store = temp_gate_store
    name = {"upper": reserved.upper(), "mixed": reserved.title(), "dot": reserved + ".",
            "space": reserved + " ", "stream": reserved + ":payload"}[variant]
    store.journal_path.write_bytes(b"pending journal must remain untouched")
    monkeypatch.setattr(store, "_recover", lambda: pytest.fail("invalid export attempted recovery"))
    before = {p: p.read_bytes() for p in store.gates_dir.parent.iterdir() if p.is_file()}
    with pytest.raises(ValueError):
        store.export_monolithic_json(store.gates_dir.parent / name)
    assert {p: p.read_bytes() for p in store.gates_dir.parent.iterdir() if p.is_file()} == before


@pytest.mark.parametrize("reserved", ["phase_gates.db", "phase_gates.db-wal", "phase_gates.db-shm",
    "phase_gates.db-journal", "gate_store.lock", "gate_store.pending.json", "gate_close.lock"])
def test_export_rejects_existing_hardlink_aliases(temp_gate_store, reserved):
    store = temp_gate_store
    protected = store.gates_dir.parent / reserved
    protected.write_bytes(b"protected")
    target = protected.with_name("snapshot.json")
    os.link(protected, target)
    with pytest.raises(ValueError):
        store.export_monolithic_json(target)
    assert protected.read_bytes() == b"protected"
    assert not store.marker_path.exists()


def test_export_rechecks_destination_under_lock(temp_gate_store, monkeypatch):
    store = temp_gate_store
    target = store.gates_dir.parent / "snapshot.json"
    store.db_path.write_bytes(b"reserved cache")
    real_enter = GateStoreLock.__enter__

    def alias_after_lock(lock):
        result = real_enter(lock)
        os.link(store.db_path, target)
        return result

    monkeypatch.setattr(GateStoreLock, "__enter__", alias_after_lock)
    with pytest.raises(ValueError):
        store.export_monolithic_json(target)
    assert store.db_path.read_bytes() == b"reserved cache"
    assert not store.marker_path.exists()


@pytest.mark.parametrize("entry", ["op_list", "op_get", "op_filter", "op_sync", "op_export", "op_bootstrap", "op_save", "op_delete", "op_update"])
def test_partial_migration_preserves_legacy_and_shard_precedence(tmp_path, monkeypatch, entry):
    monkeypatch.chdir(tmp_path)
    session = tmp_path / ".ly_state/session"
    store = GateStore(session / "gates", session / "phase_gates.db", session / "phase_gates.json")
    store.legacy_json_path.write_bytes(b'{"A":{"note":"legacy"},"B":{"keep":1}}')
    store._shard_path("A").write_bytes(b'{"phase_name":"A","note":"shard"}')
    actions = {"op_list": store.list_gates, "op_get": lambda: store.get_gate("B"),
               "op_filter": store.filter_gates, "op_sync": store.sync_cache,
               "op_export": lambda: store.export_monolithic_json(session / "snapshot.json"),
               "op_bootstrap": store.bootstrap_from_legacy_json,
               "op_save": lambda: store.save_gate("C", {}),
               "op_delete": lambda: store.delete_gate("A"),
               "op_update": lambda: update_gate._update_gate("A", {"extra": 2})}
    result = actions[entry]()
    if entry == "op_bootstrap":
        assert result == 1
        assert store.marker_path.read_bytes() == b"1\n"
    if entry == "op_get":
        assert result["keep"] == 1
    records = store.list_gates()
    assert records["B"]["keep"] == 1
    if entry != "op_delete":
        assert records["A"]["note"] == "shard"
    else:
        assert "A" not in records
    if entry == "op_save":
        assert "C" in records
    if entry == "op_update":
        assert records["A"]["extra"] == 2


@pytest.mark.parametrize("raw", [b'{', b'{"B":[]}', b'{"B":{},"B":{}}', b'{"a":{}}'], ids=["malformed", "invalid_record", "duplicate_key", "case_collision"])
def test_partial_migration_corruption_never_marks_complete(temp_gate_store, raw):
    store = temp_gate_store
    store._shard_path("A").write_bytes(b'{"phase_name":"A"}')
    store.legacy_json_path.write_bytes(raw)
    for action in (store.list_gates, store.bootstrap_from_legacy_json, lambda: store.save_gate("C", {})):
        with pytest.raises(ValueError):
            action()
    assert not store.marker_path.exists()
    assert not store.journal_path.exists()
    assert store.legacy_json_path.read_bytes() == raw
    assert store._shard_path("A").read_bytes() == b'{"phase_name":"A"}'


@pytest.mark.parametrize("stage", ["journal", "shard", "facade", "marker", "cleanup"])
def test_partial_migration_fault_replay_is_complete(temp_gate_store, monkeypatch, stage):
    store = temp_gate_store
    store._shard_path("A").write_bytes(b'{"phase_name":"A","note":"authoritative"}')
    original = store.legacy_json_path.read_bytes()
    real_write, real_unlink = gate_store._atomic_write_bytes, Path.unlink
    target = {"journal": store.journal_path, "shard": store._shard_path("GATE_BETA_20261002"),
              "facade": store.legacy_json_path, "marker": store.marker_path}.get(stage)
    with monkeypatch.context() as patch:
        def fail_write(path, raw):
            if path == target:
                raise OSError("injected migration fault")
            real_write(path, raw)
        def fail_unlink(path, *args, **kwargs):
            if stage == "cleanup" and path == store.journal_path:
                raise OSError("injected cleanup fault")
            return real_unlink(path, *args, **kwargs)
        patch.setattr(gate_store, "_atomic_write_bytes", fail_write)
        patch.setattr(Path, "unlink", fail_unlink)
        with pytest.raises((OSError, RuntimeError)):
            store.bootstrap_from_legacy_json()
    if stage == "journal":
        assert store.legacy_json_path.read_bytes() == original
        assert not store.journal_path.exists()
    if stage not in ("cleanup",):
        assert not store.marker_path.exists()
    records = store.list_gates()
    assert set(records) == {"A", "GATE_ALPHA_20261001", "GATE_BETA_20261002"}
    assert records["A"]["note"] == "authoritative"
    store.bootstrap_from_legacy_json()
    assert store.list_gates() == records
    assert json.loads(store.legacy_json_path.read_bytes()) == records
    assert not store.journal_path.exists()


@pytest.fixture
def close_repo(tmp_path, monkeypatch):
    def git(*args):
        result = subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, check=False)
        assert result.returncode == 0, result.stderr
        return result.stdout

    git("init", "-b", "feature/test")
    git("config", "user.name", "Gate test")
    git("config", "user.email", "gate@example.invalid")
    git("config", "commit.gpgsign", "false")
    git("config", "core.autocrlf", "false")
    session = tmp_path / ".ly_state/session"
    store = GateStore(session / "gates", session / "phase_gates.db", session / "phase_gates.json")
    store.legacy_json_path.write_bytes(b'{"A":{"phase_name":"A","final_verdict":"[APPROVED]"},"B":{"phase_name":"B"}}')
    (tmp_path / "source.py").write_bytes(b"pass\n")
    git("add", "source.py", ".ly_state/session/phase_gates.json")
    git("commit", "-m", "baseline")
    real_run = subprocess.run
    real_git = update_gate._git
    pushes = []

    def run(args, *rest, **kwargs):
        if args[:2] == [sys.executable, "scripts/sod_gate_enforcer.py"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        return real_run(args, *rest, **kwargs)

    def local_git(repo, *args):
        if args[0] == "push":
            pushes.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[0] == "ls-remote":
            return subprocess.CompletedProcess(args, 0, git("rev-parse", "HEAD").decode() + "\trefs/heads/feature/test", "")
        return real_git(repo, *args)

    monkeypatch.setattr(update_gate.subprocess, "run", run)
    monkeypatch.setattr(update_gate, "_git", local_git)
    return tmp_path, store, git, pushes


@pytest.mark.parametrize("deletion", ["unstaged", "staged"])
def test_close_commits_deleted_shards_and_preserves_unrelated_index(close_repo, deletion):
    repo, store, git, pushes = close_repo
    store.bootstrap_from_legacy_json()
    git("add", ".ly_state/session/gates")
    git("commit", "-m", "migration")
    store.delete_gate("B")
    deleted = ".ly_state/session/gates/B.json"
    if deletion == "staged":
        git("add", "-u", "--", deleted)
    (repo / "unrelated.py").write_bytes(b"keep staged\n")
    git("add", "unrelated.py")
    unrelated = git("ls-files", "--stage", "--", "unrelated.py")
    head = update_gate.close_gate_transaction("A", ["source.py"], "delete B", repo)
    assert git("ls-tree", "-r", "--name-only", head, "--", deleted) == b""
    assert git("ls-files", "--stage", "--", "unrelated.py") == unrelated
    assert len(pushes) == 1
    checkout = repo / "checkout"
    checkout.mkdir()
    for relative in git("ls-tree", "-r", "--name-only", head).decode().splitlines():
        target = checkout / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git("show", f"{head}:{relative}"))
    session = checkout / ".ly_state/session"
    fresh = GateStore(session / "gates", session / "phase_gates.db", session / "phase_gates.json")
    assert set(fresh.list_gates()) == {"A"}


@pytest.mark.parametrize("layout", ["legacy", "partial", "initialized", "legacy_sources"])
def test_close_stages_new_migration_artifacts(close_repo, layout):
    repo, store, git, pushes = close_repo
    if layout == "partial":
        store._shard_path("A").write_bytes(b'{"phase_name":"A","final_verdict":"[APPROVED]"}')
    elif layout == "initialized":
        store.bootstrap_from_legacy_json()
    elif layout == "legacy_sources":
        records = json.loads(store.legacy_json_path.read_bytes())
        records["B"]["repo_local_skill_sources"] = ".agents/agent/backend-engineer.md; .agents/skills/python-patterns/skill.md"
        store.legacy_json_path.write_text(json.dumps(records), encoding="utf-8")
    head = update_gate.close_gate_transaction("A", ["source.py"], "migrate", repo)
    assert git("show", f"{head}:.ly_state/session/gates/.initialized") == b"1\n"
    assert json.loads(git("show", f"{head}:.ly_state/session/gates/B.json"))["phase_name"] == "B"
    assert len(pushes) == 1


@pytest.mark.parametrize("failure", ["tracked_lookup", "index_lookup", "staging", "resurrection", "disappearance", "extra_shard", "secret", "secret_json", "commit", "tree_resurrection", "tree_lookup"])
def test_close_artifact_faults_never_push(close_repo, monkeypatch, failure):
    repo, store, git, pushes = close_repo
    store.bootstrap_from_legacy_json()
    git("add", ".ly_state/session/gates")
    git("commit", "-m", "migration")
    removed = store._shard_path("B")
    previous = removed.read_bytes()
    store.delete_gate("B")
    baseline = git("rev-parse", "HEAD")
    real_git, real_bytes, real_run = update_gate._git, update_gate._git_bytes, subprocess.run

    def faulty_git(root, *args):
        if failure == "staging" and args[0] == "add":
            return subprocess.CompletedProcess(args, 1, "", "injected staging failure")
        if failure == "commit" and args[0] == "commit":
            return subprocess.CompletedProcess(args, 1, "", "injected commit failure")
        if failure in ("tree_resurrection", "tree_lookup") and args[0] == "ls-tree" and args[-1].endswith("B.json"):
            return subprocess.CompletedProcess(args, int(failure == "tree_lookup"), ".ly_state/session/gates/B.json\n", "")
        return real_git(root, *args)

    def faulty_bytes(root, *args):
        if (failure == "tracked_lookup" and args[0] == "ls-tree") or (failure == "index_lookup" and args[0] == "ls-files"):
            return subprocess.CompletedProcess(args, 1, b"", b"injected lookup failure")
        return real_bytes(root, *args)

    def faulty_run(args, *rest, **kwargs):
        if args[:2] == [sys.executable, "scripts/sod_gate_enforcer.py"]:
            if failure == "resurrection":
                removed.write_bytes(previous)
            elif failure == "disappearance":
                store._shard_path("A").unlink()
            elif failure == "extra_shard":
                store._shard_path("C").write_bytes(b'{"phase_name":"C"}')
            return subprocess.CompletedProcess(args, 0, "", "")
        return real_run(args, *rest, **kwargs)

    if failure in ("secret", "secret_json"):
        quote = '"' if failure == "secret_json" else "'"
        store.save_gate("C", {"note": f"api_key={quote}abcdefghijklmnopqrstuvxyz{quote}"})
    monkeypatch.setattr(update_gate, "_git", faulty_git)
    monkeypatch.setattr(update_gate, "_git_bytes", faulty_bytes)
    monkeypatch.setattr(update_gate.subprocess, "run", faulty_run)
    with pytest.raises(RuntimeError):
        update_gate.close_gate_transaction("A", ["source.py"], "must not push", repo)
    assert pushes == []
    assert not store.legacy_json_path.with_name("gate_close.lock").exists()
    if failure not in ("tree_resurrection", "tree_lookup"):
        assert git("rev-parse", "HEAD") == baseline


@pytest.mark.parametrize("layout", ["legacy", "shard"])
@pytest.mark.parametrize("entry", ["op_list", "get", "filter", "sync", "export", "bootstrap", "save", "delete", "update"])
def test_legacy_semicolon_sources_normalized_across_store(tmp_path, monkeypatch, entry, layout):
    monkeypatch.chdir(tmp_path)
    session = tmp_path / ".ly_state/session"
    store = GateStore(session / "gates", session / "phase_gates.db", session / "phase_gates.json")
    sources = [".agents/agent/backend-engineer.md", ".agents/skills/python-patterns/skill.md"]
    legacy = {"A": {"repo_local_skill_sources": " ; " + " ; ".join(sources) + " ; ", "keep": 1}, "B": {"keep": 2}}
    store.legacy_json_path.write_text(json.dumps(legacy), encoding="utf-8")
    if layout == "shard":
        store._shard_path("A").write_text(json.dumps({"phase_name": "A", **legacy["A"]}), encoding="utf-8")
    actions = {"op_list": store.list_gates, "get": lambda: store.get_gate("A"),
               "filter": store.filter_gates, "sync": store.sync_cache,
               "export": lambda: store.export_monolithic_json(session / "snapshot.json"),
               "bootstrap": store.bootstrap_from_legacy_json,
               "save": lambda: store.save_gate("C", {"repo_local_skill_sources": ";".join(sources)}),
               "delete": lambda: store.delete_gate("B"),
               "update": lambda: update_gate._update_gate("A", {"note": "updated"})}
    actions[entry]()
    assert store.get_gate("A")["repo_local_skill_sources"] == sources
    assert store.get_gate("A")["keep"] == 1
    assert store.filter_gates()[0]["repo_local_skill_sources"] == sources
    if entry == "save":
        assert store.get_gate("C")["repo_local_skill_sources"] == sources


@pytest.mark.parametrize("target", ["shard", "legacy", "marker"])
def test_legacy_source_normalization_survives_publication_recovery(temp_gate_store, monkeypatch, target):
    store = temp_gate_store
    write = gate_store._atomic_write_bytes
    paths = {"shard": store._shard_path("C"), "legacy": store.legacy_json_path, "marker": store.marker_path}
    def fail(path, raw):
        if path == paths[target]:
            raise OSError("injected normalization publication failure")
        write(path, raw)
    with monkeypatch.context() as patch:
        patch.setattr(gate_store, "_atomic_write_bytes", fail)
        with pytest.raises(RuntimeError, match="recovery required"):
            store.save_gate("C", {"repo_local_skill_sources": " a ; b ; "})
    assert store.get_gate("C")["repo_local_skill_sources"] == ["a", "b"]
    assert json.loads(store.legacy_json_path.read_bytes())["C"]["repo_local_skill_sources"] == ["a", "b"]
    assert not store.journal_path.exists()


@pytest.mark.parametrize("value, expected", [(None, None), ("", []), (" ; ; ", []), ([], []),
                                           (["a", "b"], ["a", "b"]), (" a ; b ", ["a", "b"])])
def test_record_skill_source_forms_detach_input(value, expected):
    record = {"repo_local_skill_sources": value}
    original = json.dumps(record)
    normalized = gate_store._record("A", record)
    assert normalized["repo_local_skill_sources"] == expected
    assert json.dumps(record) == original


@pytest.mark.parametrize("value", [False, 0, 1e13, {}, [None], [1], [["a"]], float("nan"), float("inf"), -float("inf")])
def test_legacy_source_malformed_values_do_not_publish(temp_gate_store, value):
    store = temp_gate_store
    before = store.legacy_json_path.read_bytes()
    with pytest.raises(ValueError):
        store.save_gate("C", {"repo_local_skill_sources": value})
    assert store.legacy_json_path.read_bytes() == before
    assert not store.journal_path.exists()


@pytest.mark.parametrize("layout", ["legacy", "partial", "initialized", "empty"])
def test_close_scope_recreates_complete_checkout(tmp_path, monkeypatch, layout):
    monkeypatch.setattr(update_gate, "_git_bytes", lambda repo, *args: subprocess.CompletedProcess(args, 0, b"", b""))
    monkeypatch.setattr(update_gate, "_git", lambda repo, *args: subprocess.CompletedProcess(args, 0, "", ""))

    session = tmp_path / ".ly_state/session"
    store = GateStore(session / "gates", session / "phase_gates.db", session / "phase_gates.json")
    store.legacy_json_path.write_bytes(b'{"A":{"phase_name":"A","final_verdict":"[APPROVED]"},"B":{"phase_name":"B"}}')
    if layout == "partial":
        store._shard_path("A").write_bytes(b'{"phase_name":"A","final_verdict":"[APPROVED]"}')
    if layout in ("initialized", "empty"):
        store.bootstrap_from_legacy_json()
    if layout == "empty":
        store.delete_gate("A", sync_legacy=False)
        store.delete_gate("B", sync_legacy=False)
    source = tmp_path / "source.py"
    source.write_bytes(b"pass\n")
    seen = []
    monkeypatch.setattr(update_gate, "_close_gate_locked", lambda gate, paths, *args: seen.extend(paths) or "fake")
    if layout == "empty":
        seen = update_gate._close_scope(tmp_path, ["source.py"])
    else:
        assert update_gate.close_gate_transaction("A", ["source.py"], "message", tmp_path) == "fake"
    assert ".ly_state/session/gates/.initialized" in seen
    assert not any(p.endswith((".db", ".lock", ".pending.json")) for p in seen)
    checkout = tmp_path / "checkout"
    for relative in seen:
        dest = checkout / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((tmp_path / relative).read_bytes())
    fresh_session = checkout / ".ly_state/session"
    fresh = GateStore(fresh_session / "gates", fresh_session / "phase_gates.db", fresh_session / "phase_gates.json")
    expected = set() if layout == "empty" else {"A", "B"}
    assert set(fresh.list_gates()) == expected
    fresh.save_gate("C", {})
    assert set(json.loads(fresh.legacy_json_path.read_bytes())) == expected | {"C"}


def test_close_verifies_changed_subset_and_all_authoritative_blobs(tmp_path, monkeypatch):
    session = tmp_path / ".ly_state/session"
    store = GateStore(session / "gates", session / "phase_gates.db", session / "phase_gates.json")
    store.legacy_json_path.write_bytes(b'{"A":{"phase_name":"A","final_verdict":"[APPROVED]"},"B":{"phase_name":"B"}}')
    store.bootstrap_from_legacy_json()
    source = tmp_path / "source.py"
    source.write_bytes(b"pass\n")
    paths = update_gate._close_scope(tmp_path, ["source.py"])
    changed = ["source.py", ".ly_state/session/phase_gates.json", ".ly_state/session/gates/A.json"]
    head, new_head = "a" * 40, "b" * 40
    committed = False
    blobs = {}
    checked = []
    real_run = subprocess.run

    def fake_git(repo, *args):
        nonlocal committed
        output = ""
        if args == ("branch", "--show-current"):
            output = "feature/test"
        elif args == ("rev-parse", "HEAD"):
            output = new_head if committed else head
        elif args == ("rev-parse", new_head + "^"):
            output = head
        elif args[:2] == ("diff", "--binary"):
            output = "diff --git a/source.py b/source.py"
        elif args[:2] == ("diff", "--name-only") or args[0] == "diff-tree":
            output = "\n".join(changed)
        elif args[0] == "commit":
            assert set(args[args.index("--") + 1:]) == set(paths)
            committed = True
        elif args[0] == "rev-parse" and args[1].startswith(new_head + ":"):
            relative = args[1].split(":", 1)[1]
            checked.append(relative)
            oid = f"{len(blobs) + 1:040x}"
            blobs[oid] = (repo / relative).read_bytes()
            output = oid
        elif args[0] == "ls-remote":
            output = new_head + "\trefs/heads/feature/test"
        elif args[0] not in ("push", "add"):
            pytest.fail(f"unexpected git call: {args}")
        return subprocess.CompletedProcess(args, 0, output, "")

    def fake_run(args, *rest, **kwargs):
        if args[:2] == [sys.executable, "scripts/sod_gate_enforcer.py"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        return real_run(args, *rest, **kwargs)

    monkeypatch.setattr(update_gate, "_git", fake_git)
    monkeypatch.setattr(update_gate, "_git_bytes", lambda repo, *args: subprocess.CompletedProcess(args, 0, blobs[args[-1]] if args[0] == "cat-file" else b"", b""))
    monkeypatch.setattr(update_gate.subprocess, "run", fake_run)
    assert update_gate.close_gate_transaction("A", ["source.py"], "message", tmp_path) == new_head
    assert set(checked) == set(paths)
    assert ".ly_state/session/gates/B.json" in checked
    assert ".ly_state/session/gates/.initialized" in checked


@pytest.mark.parametrize("failure", ["migration", "artifact", "mismatch"])
def test_close_fails_before_git_for_incomplete_publication(tmp_path, monkeypatch, failure):
    session = tmp_path / ".ly_state/session"
    store = GateStore(session / "gates", session / "phase_gates.db", session / "phase_gates.json")
    store.legacy_json_path.write_bytes(b'{"A":{"phase_name":"A","final_verdict":"[APPROVED]"},"B":{"phase_name":"B"}}')
    source = tmp_path / "source.py"
    source.write_bytes(b"pass\n")
    monkeypatch.setattr(update_gate, "_close_gate_locked", lambda *args: pytest.fail("git reached"))
    if failure == "migration":
        real_write = gate_store._atomic_write_bytes
        def fail_marker(path, raw):
            if path == store.marker_path:
                raise OSError("marker fault")
            real_write(path, raw)
        monkeypatch.setattr(gate_store, "_atomic_write_bytes", fail_marker)
    elif failure == "artifact":
        (store.gates_dir / "B.json").mkdir()
    else:
        store._shard_path("A").write_bytes(b'{"phase_name":"A","note":"mismatched"}')
    with pytest.raises((RuntimeError, ValueError)):
        update_gate.close_gate_transaction("A", ["source.py"], "message", tmp_path)
    assert not session.joinpath("gate_close.lock").exists()
    if failure == "migration":
        assert store.journal_path.exists()
        assert not store.marker_path.exists()


def test_partial_migration_concurrent_readers_and_writers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session = tmp_path / ".ly_state/session"
    store = GateStore(session / "gates", session / "phase_gates.db", session / "phase_gates.json")
    store.legacy_json_path.write_bytes(b'{"A":{"keep":1},"B":{"keep":2}}')
    store._shard_path("A").write_bytes(b'{"phase_name":"A","keep":3}')
    def worker(index):
        if index == 0:
            store.bootstrap_from_legacy_json()
        elif index == 1:
            assert store.get_gate("B")["keep"] == 2
        else:
            update_gate._update_gate("A", {f"field{index}": index})
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(worker, range(6)))
    records = store.list_gates()
    assert records["A"]["keep"] == 3
    assert records["B"]["keep"] == 2
    assert all(records["A"][f"field{i}"] == i for i in range(2, 6))
    assert json.loads(store.legacy_json_path.read_bytes()) == records


def test_resource_bounds_and_export_reserved_paths(temp_gate_store, monkeypatch):
    store = temp_gate_store
    with monkeypatch.context() as patch:
        patch.setattr(gate_store, "MAX_JSON_BYTES", 20)
        with pytest.raises(ValueError, match="size limit"):
            store.save_gate("GATE", {"note": "x" * 21})
    for target in (store.db_path, store.lock_path, store.journal_path, store.gates_dir / "GATE.json"):
        with pytest.raises(ValueError):
            store.export_monolithic_json(target)


@pytest.mark.parametrize("raw", [b'{}', b'{"records":{},"changes":["../bad"],"legacy":true}',
    b'{"records":{},"changes":["GATE","GATE"],"legacy":true}'])
def test_invalid_recovery_journal_refuses_mutation(temp_gate_store, raw):
    store = temp_gate_store
    before = store.legacy_json_path.read_bytes()
    store.journal_path.write_bytes(raw)
    with pytest.raises(ValueError):
        store.list_gates()
    assert store.legacy_json_path.read_bytes() == before


@pytest.mark.parametrize("timeout", [None, True, -1, float("nan"), float("inf"), "1"])
def test_lock_timeout_validation(tmp_path, timeout):
    with pytest.raises(ValueError):
        GateStoreLock(tmp_path / "lock", timeout)


@pytest.mark.parametrize("tamper", ["digest", "target", "non_target"])
def test_recovery_rejects_tampering(temp_gate_store, monkeypatch, tamper):
    store = temp_gate_store
    store.bootstrap_from_legacy_json()
    real_write = gate_store._atomic_write_bytes
    with monkeypatch.context() as patch:
        def stop_at_facade(path, raw):
            if path == store.legacy_json_path:
                raise OSError("stop replay")
            real_write(path, raw)
        patch.setattr(gate_store, "_atomic_write_bytes", stop_at_facade)
        with pytest.raises(RuntimeError):
            store.save_gate("GATE_ALPHA_20261001", {"note": "committed"})
    if tamper == "digest":
        journal = json.loads(store.journal_path.read_bytes())
        journal["records"]["GATE_ALPHA_20261001"]["note"] = "tampered"
        store.journal_path.write_bytes(json.dumps(journal).encode())
    else:
        name = "GATE_ALPHA_20261001" if tamper == "target" else "GATE_BETA_20261002"
        store._shard_path(name).write_bytes(json.dumps({"phase_name": name, "note": "tampered"}).encode())
    before = store.legacy_json_path.read_bytes()
    with pytest.raises(ValueError):
        store.list_gates()
    assert store.journal_path.exists()
    assert store.legacy_json_path.read_bytes() == before


def test_hybrid_close_binds_shard_without_committing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session = tmp_path / ".ly_state/session"
    store = GateStore(session / "gates", session / "phase_gates.db", session / "phase_gates.json")
    store.save_gate("GATE", {"final_verdict": "[APPROVED]"})
    source = tmp_path / "source.py"
    source.write_bytes(b"pass\n")
    seen = []
    monkeypatch.setattr(update_gate, "_close_gate_locked", lambda gate, paths, *args: seen.extend(paths) or "fake")
    assert update_gate.close_gate_transaction("GATE", ["source.py"], "message", tmp_path) == "fake"
    assert ".ly_state/session/gates/GATE.json" in seen
    store._shard_path("GATE").write_bytes(b'{"phase_name":"GATE","final_verdict":"[NEEDS_FIX]"}')
    with pytest.raises(RuntimeError, match="disagree"):
        update_gate.close_gate_transaction("GATE", ["source.py"], "message", tmp_path)


@pytest.mark.parametrize("invalid", ["../BAD", "--flag", ""])
def test_updater_cli_fails_closed_for_bad_identifiers(tmp_path, monkeypatch, invalid):
    monkeypatch.chdir(tmp_path)
    session = tmp_path / ".ly_state/session"
    session.mkdir(parents=True)
    original = b'{}'
    session.joinpath("phase_gates.json").write_bytes(original)
    monkeypatch.setattr(update_gate.sys, "argv", ["update_gate.py", invalid, "note=secret"])
    with pytest.raises(SystemExit) as exc:
        update_gate.main()
    assert exc.value.code == 1
    assert session.joinpath("phase_gates.json").read_bytes() == original


def test_updater_metadata_boundary_and_secret_safe_output(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    session = tmp_path / ".ly_state/session"
    session.mkdir(parents=True)
    session.joinpath("phase_gates.json").write_bytes(b'{}')
    gate = "GATE_20261015"
    update_gate._update_gate(gate, {"l3_session_id": "l3_session", "note": "credential-value"})
    assert "credential-value" not in capsys.readouterr().out
    before = session.joinpath("phase_gates.json").read_bytes()
    with pytest.raises(RuntimeError):
        update_gate._update_gate(gate, {"timestamp": "2026-10-14T15:30:00+07:00"})
    assert session.joinpath("phase_gates.json").read_bytes() == before


@pytest.mark.parametrize("name", ["CON", "NUL.txt", "COM1", "LPT9", "GATE."])
def test_windows_reserved_identifiers_rejected(temp_gate_store, name):
    with pytest.raises(ValueError, match="identifier"):
        temp_gate_store.save_gate(name, {})


def test_case_collision_rejected_before_publication(temp_gate_store):
    store = temp_gate_store
    store.legacy_json_path.write_bytes(b'{"GATE":{},"gate":{}}')
    with pytest.raises(ValueError, match="Case-colliding"):
        store.bootstrap_from_legacy_json()
    assert not store.journal_path.exists()


def test_cache_index_tampering_and_transaction_rollback(temp_gate_store, monkeypatch):
    store = temp_gate_store
    store.bootstrap_from_legacy_json()
    store.sync_cache()
    from contextlib import closing
    with closing(store._get_connection()) as conn:
        with conn:
            conn.execute("UPDATE gates SET final_verdict = 'forged'")
    assert len(store.filter_gates("[APPROVED]")) == 1
    original_connect = store._get_connection

    class FailCommit:
        def __init__(self):
            self.conn = original_connect()
        def __getattr__(self, name):
            return getattr(self.conn, name)
        def __enter__(self):
            self.conn.__enter__()
            return self
        def __exit__(self, *args):
            self.conn.rollback()
            raise RuntimeError("injected cache commit failure")

    with monkeypatch.context() as patch:
        patch.setattr(store, "_get_connection", FailCommit)
        with pytest.raises(RuntimeError, match="cache commit"):
            store.save_gate("NEW", {})
    with closing(original_connect()) as conn:
        assert conn.execute("SELECT count(*) FROM gates WHERE phase_name='NEW'").fetchone()[0] == 0
    assert store.get_gate("NEW") == {"phase_name": "NEW"}


def test_symlink_paths_fail_closed(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="symlink"):
        GateStore(link / "gates", link / "phase_gates.db", link / "phase_gates.json")
    assert not (real / "gates").exists()


def test_corrupt_initialization_marker_blocks_legacy_fallback(temp_gate_store):
    store = temp_gate_store
    store.marker_path.write_bytes(b"partial")
    with pytest.raises(ValueError, match="initialization marker"):
        store.list_gates()
    with pytest.raises(ValueError, match="initialization marker"):
        store.bootstrap_from_legacy_json()


def test_real_process_crash_after_journal_is_recoverable(temp_gate_store):
    store = temp_gate_store
    store.bootstrap_from_legacy_json()
    code = (
        "from pathlib import Path; from scripts import gate_store as g; import os,sys; "
        "s=g.GateStore(*(Path(p) for p in sys.argv[1:])); real=g._atomic_write_bytes; "
        "g._atomic_write_bytes=lambda p,b: os._exit(23) if p==s.legacy_json_path else real(p,b); "
        "s.save_gate('CRASHED',{'note':'committed'})"
    )
    result = subprocess.run([sys.executable, "-c", code, str(store.gates_dir), str(store.db_path),
                             str(store.legacy_json_path)], cwd=Path(__file__).resolve().parents[1], timeout=15)
    assert result.returncode == 23
    assert store.journal_path.exists()
    assert store.get_gate("CRASHED")["note"] == "committed"
    assert not store.journal_path.exists()
