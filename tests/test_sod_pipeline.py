import hashlib
import json
import shutil
from pathlib import Path

import pytest

import scripts.sod_pipeline as pipeline

GRAPH_ARTIFACT = ".ly_state/session/graph_evidence_l2_role11_sod_pipeline_standardization_20260922.json"


@pytest.fixture(autouse=True)
def _successful_pre_audit_validation(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "capture",
        lambda command: (0, "PRE_AUDIT_PATH=x\nPRE_AUDIT_SHA256=" + "a" * 64),
    )


@pytest.mark.skipif(shutil.which("powershell") is None, reason="Windows PowerShell is required for subprocess boundary tests")
def test_run_powershell_block_propagates_explicit_exit_code(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    assert pipeline.run("if ($true) { exit 7 }", "fault", check=False) == 7


@pytest.mark.skipif(shutil.which("powershell") is None, reason="Windows PowerShell is required for subprocess boundary tests")
def test_run_powershell_block_maps_terminating_error_to_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    assert pipeline.run("throw 'fault'", "fault", check=False) != 0


@pytest.mark.skipif(shutil.which("powershell") is None, reason="Windows PowerShell is required for subprocess boundary tests")
def test_run_powershell_block_clean_exit_is_not_masked_by_stale_exit_code(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    assert pipeline.run("$global:LASTEXITCODE = 9; Write-Output 'clean'", "clean", check=False) == 0


def test_l2_dispatch_passes_model_as_an_argument(monkeypatch):
    args = pipeline.parse_args(["worker", "auditor", "GATE", "slug", "task", "file.py", "--model", "lead/model"])
    seen = []
    monkeypatch.setattr(pipeline, "capture", lambda command: (seen.append(command) or (0, "SESSION_ID=x\nROLE_ID=11\nROLE_NAME=worker\nGATE=GATE\nMODEL=m\nRISK=high\nANTI_DRIP_MODE=remediation\nANTI_DRIP_CONTRACT=x\nANTI_DRIP_CONTRACT_SHA256=" + "a" * 64 + "\n---COMMAND---\nrun")))
    pipeline._dispatch_l2(args, args.task)
    assert len(pipeline._read_graph_evidence_sha256(GRAPH_ARTIFACT)) == 64
    assert seen[0][-2:] == ["--model", "lead/model"]
    assert all("\"task\"" not in value for value in seen[0])


def test_l2_dispatch_passes_dry_run_as_an_argument(monkeypatch):
    args = pipeline.parse_args(["worker", "auditor", "GATE", "slug", "task", "file.py", "--dry-run"])
    seen = []
    monkeypatch.setattr(pipeline, "capture", lambda command: (seen.append(command) or (0, "SESSION_ID=x\nROLE_ID=11\nROLE_NAME=worker\nGATE=GATE\nMODEL=m\nRISK=high\nANTI_DRIP_MODE=remediation\nANTI_DRIP_CONTRACT=x\nANTI_DRIP_CONTRACT_SHA256=" + "a" * 64 + "\n---COMMAND---\nrun")))
    pipeline._dispatch_l2(args, args.task)
    assert seen[0][-1] == "--dry-run"


def test_plan_aliases_default_and_enable():
    assert pipeline.parse_args(["worker", "auditor", "GATE", "slug", "task", "file.py"]).with_plan is False
    assert pipeline.parse_args(["worker", "auditor", "GATE", "slug", "task", "file.py", "--with-plan"]).with_plan is True
    assert pipeline.parse_args(["worker", "auditor", "GATE", "slug", "task", "file.py", "--plan"]).with_plan is True


def test_plan_validator_requires_fresh_identity_and_exact_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    (tmp_path / "file.py").write_text("x", encoding="utf-8")
    valid = """# Implementation Plan
## Planning Run ID
run-1
## Gate
GATE
## Goal
goal
## Authorized Scope
- file.py
## Technical Design
design
## Verification Plan
tests
"""
    assert pipeline._validate_plan(valid, "run-1", "GATE", "file.py") == valid
    with pytest.raises(RuntimeError, match="run id mismatch"):
        pipeline._validate_plan(valid.replace("run-1", "old"), "run-1", "GATE", "file.py")
    with pytest.raises(RuntimeError, match="heading cardinality"):
        pipeline._validate_plan(valid + "\n## Unknown\nvalue\n", "run-1", "GATE", "file.py")


def test_phase_zero_failure_blocks_l2(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    called = []
    monkeypatch.setattr(pipeline, "_run_planning_phase", lambda args: (_ for _ in ()).throw(RuntimeError("planner failed")))
    monkeypatch.setattr(pipeline, "_dispatch_l2", lambda *args: called.append("l2"))
    assert pipeline.main(["worker", "auditor", "GATE", "slug", "task", "file.py", "--with-plan"]) == 2
    assert called == []


def _planning_args():
    return pipeline.parse_args(["worker", "auditor", "GATE", "slug", "task", "file.py", "--with-plan"])


def _valid_planner_output(run_id):
    return f"""# Implementation Plan
## Planning Run ID
{run_id}
## Gate
GATE
## Goal
goal
## Authorized Scope
- file.py
## Technical Design
design
## Verification Plan
tests
"""


def test_plan_path_rejects_symlink_and_reparse(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    session = tmp_path / ".ly_state" / "session"
    session.mkdir(parents=True)
    plan = session / "implementation_plan.md"
    plan.write_text("old", encoding="utf-8")
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == plan)
    with pytest.raises(RuntimeError, match="identity invalid"):
        pipeline._plan_path()
    monkeypatch.setattr(Path, "is_symlink", lambda self: False)
    monkeypatch.setattr(Path, "lstat", lambda self: type("Stat", (), {"st_file_attributes": 0x400, "st_nlink": 1})())
    with pytest.raises(RuntimeError, match="identity invalid"):
        pipeline._plan_path()


def test_planning_resets_stale_plan_before_spawn_and_publishes_durably(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    (tmp_path / "file.py").write_text("x", encoding="utf-8")
    plan = tmp_path / ".ly_state" / "session" / "implementation_plan.md"
    plan.parent.mkdir(parents=True)
    plan.write_text("stale", encoding="utf-8")
    seen = []

    def fake_run(*args, **kwargs):
        seen.append(plan.exists())
        run_id = kwargs["input"].decode().split("PLANNING_RUN_ID: ", 1)[1].split("\n", 1)[0]
        return type("Result", (), {"returncode": 0, "stdout": _valid_planner_output(run_id).encode(), "stderr": b""})()

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)
    pipeline._run_planning_phase(_planning_args())
    assert seen == [False]
    assert plan.read_text(encoding="utf-8").startswith("# Implementation Plan")


def test_planner_invalid_utf8_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipeline.subprocess, "run", lambda *a, **k: type("Result", (), {"returncode": 0, "stdout": b"\xff", "stderr": b""})())
    with pytest.raises(RuntimeError, match="valid UTF-8"):
        pipeline._run_planning_phase(_planning_args())


def test_planner_error_redacts_bounded_secrets(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipeline.subprocess, "run", lambda *a, **k: type("Result", (), {"returncode": 1, "stdout": b"", "stderr": b"Bearer secret-token-123"})())
    with pytest.raises(RuntimeError) as excinfo:
        pipeline._run_planning_phase(_planning_args())
    assert "secret-token-123" not in str(excinfo.value)
    assert "[REDACTED]" in str(excinfo.value)


def test_main_dry_run_uses_bound_artifact_and_tolerates_dirty_scope(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    artifact = tmp_path / "evidence.json"
    artifact.write_text(json.dumps({"scope_files": ["file.py"], "scope_dirty": True}), encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    artifact.with_suffix(".sha256").write_text(digest, encoding="ascii")
    monkeypatch.setattr(pipeline, "verify_graph_evidence", lambda *args, **kwargs: {"path": "evidence.json"})
    monkeypatch.setattr(pipeline, "_dispatch_l2", lambda args, task: ({"SESSION_ID": "session"}, "echo dry-run"))
    assert pipeline.main(["worker", "auditor", "GATE", "slug", "task", "file.py", "--graph-evidence", "evidence.json", "--dry-run"]) == 0
    assert capsys.readouterr().out.strip().endswith("echo dry-run")


def test_graph_evidence_digest_is_read_from_sidecar(tmp_path, monkeypatch):
    artifact = tmp_path / "evidence.json"
    artifact.write_text("{}", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    artifact.with_suffix(".sha256").write_text(digest + "\n", encoding="ascii")
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    assert pipeline._read_graph_evidence_sha256("evidence.json") == digest


def test_verify_graph_evidence_accepts_clean_sidecar_bound_artifact(tmp_path, monkeypatch):
    source_root = Path(pipeline.REPO_ROOT)
    source = json.loads((source_root / GRAPH_ARTIFACT).read_text(encoding="utf-8"))
    source["scope_dirty"] = False
    for relative_path in source["scope_files"]:
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source_root / relative_path).read_bytes())
    source["scope_content_hashes"] = {
        relative_path: hashlib.sha256((tmp_path / relative_path).read_bytes()).hexdigest()
        for relative_path in source["scope_files"]
    }
    artifact = tmp_path / "evidence.json"
    artifact.write_text(json.dumps(source), encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    artifact.with_suffix(".sha256").write_text(digest, encoding="ascii")
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipeline.subprocess, "check_output", lambda *args, **kwargs: source["repo_commit"] + "\n")
    verified = pipeline.verify_graph_evidence("evidence.json")
    assert verified["scope_dirty"] is False
    assert verified["sha256"] == digest


@pytest.mark.parametrize("output", [
    "SESSION_ID=x\nSESSION_ID=y\nROLE_ID=11",
    "SESSION_ID=x\nUNEXPECTED=y\nROLE_ID=11",
    "SESSION_ID=x\n=bad\nROLE_ID=11",
    "SESSION_ID=x\nROLE_ID=",
])
def test_parse_dispatch_output_rejects_mutated_l2_metadata(output):
    with pytest.raises(ValueError):
        pipeline.parse_dispatch_output(output, required={"SESSION_ID", "ROLE_ID"})


@pytest.mark.parametrize("output", [
    "L3_SESSION_ID=x\nL3_ROLE_ID=21\nREPORT=",
    "L3_SESSION_ID=x\nL3_ROLE_ID=21\nREPORT=x\nROLE_ID=11",
    "L3_SESSION_ID=x\nL3_SESSION_ID=y\nL3_ROLE_ID=21\nREPORT=x",
])
def test_parse_dispatch_output_rejects_mutated_l3_metadata(output):
    with pytest.raises(ValueError):
        pipeline.parse_dispatch_output(output, required={"L3_SESSION_ID", "L3_ROLE_ID", "REPORT"})


def test_verify_graph_evidence_rejects_schema_mutation_and_protects_trusted_fields(tmp_path, monkeypatch):
    source = Path(pipeline.REPO_ROOT) / GRAPH_ARTIFACT
    evidence = json.loads(source.read_text(encoding="utf-8"))
    evidence["scope_files"] = ["scripts/sod_pipeline.py", 7]
    evidence["path"] = "attacker-path"
    artifact = tmp_path / "evidence.json"
    artifact.write_text(json.dumps(evidence), encoding="utf-8")
    artifact.with_suffix(".sha256").write_text(hashlib.sha256(artifact.read_bytes()).hexdigest(), encoding="ascii")
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipeline.subprocess, "check_output", lambda *args, **kwargs: "f4cb23ad18b8b5015d186e4aaf032347d455fdf5\n")
    with pytest.raises(RuntimeError, match="schema mismatch|scope mismatch"):
        pipeline.verify_graph_evidence("evidence.json")


def test_verify_graph_evidence_rejects_dirty_scope(tmp_path, monkeypatch):
    source = Path(pipeline.REPO_ROOT) / GRAPH_ARTIFACT
    evidence = json.loads(source.read_text(encoding="utf-8"))
    evidence["scope_dirty"] = True
    artifact = tmp_path / "evidence.json"
    artifact.write_text(json.dumps(evidence), encoding="utf-8")
    artifact.with_suffix(".sha256").write_text(hashlib.sha256(artifact.read_bytes()).hexdigest(), encoding="ascii")
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="scope mismatch"):
        pipeline.verify_graph_evidence("evidence.json")


def test_verify_graph_evidence_rejects_scope_content_mutation(tmp_path, monkeypatch):
    source_root = Path(pipeline.REPO_ROOT)
    evidence = json.loads((source_root / GRAPH_ARTIFACT).read_text(encoding="utf-8"))
    evidence["scope_dirty"] = False
    evidence["scope_dirty"] = False
    for relative_path in evidence["scope_files"]:
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source_root / relative_path).read_bytes())
    evidence["scope_content_hashes"] = {
        relative_path: hashlib.sha256((tmp_path / relative_path).read_bytes()).hexdigest()
        for relative_path in evidence["scope_files"]
    }
    (tmp_path / evidence["scope_files"][0]).write_bytes(
        (tmp_path / evidence["scope_files"][0]).read_bytes() + b"\nmutation"
    )
    artifact = tmp_path / "evidence.json"
    artifact.write_text(json.dumps(evidence), encoding="utf-8")
    artifact.with_suffix(".sha256").write_text(hashlib.sha256(artifact.read_bytes()).hexdigest(), encoding="ascii")
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipeline.subprocess, "check_output", lambda *args, **kwargs: evidence["repo_commit"] + "\n")
    with pytest.raises(RuntimeError, match="content hash mismatch"):
        pipeline.verify_graph_evidence("evidence.json")


def test_verify_graph_evidence_rejects_blast_radius_query_mutation(tmp_path, monkeypatch):
    source_root = Path(pipeline.REPO_ROOT)
    evidence = json.loads((source_root / GRAPH_ARTIFACT).read_text(encoding="utf-8"))
    evidence["scope_dirty"] = False
    for relative_path in evidence["scope_files"]:
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source_root / relative_path).read_bytes())
    evidence["scope_content_hashes"] = {
        relative_path: hashlib.sha256((tmp_path / relative_path).read_bytes()).hexdigest()
        for relative_path in evidence["scope_files"]
    }
    evidence["blast_radius"]["impacted_files"] = ["unexpected.py"]
    evidence["blast_radius"]["total_impacted"] = 1
    artifact = tmp_path / "evidence.json"
    artifact.write_text(json.dumps(evidence), encoding="utf-8")
    artifact.with_suffix(".sha256").write_text(hashlib.sha256(artifact.read_bytes()).hexdigest(), encoding="ascii")
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipeline.subprocess, "check_output", lambda *args, **kwargs: evidence["repo_commit"] + "\n")
    with pytest.raises(RuntimeError, match="blast/query mismatch"):
        pipeline.verify_graph_evidence("evidence.json")


def _mutated_graph_evidence(tmp_path, monkeypatch, mutate):
    source_root = Path(pipeline.REPO_ROOT)
    evidence = json.loads((source_root / GRAPH_ARTIFACT).read_text(encoding="utf-8"))
    evidence["scope_dirty"] = False
    for relative_path in evidence["scope_files"]:
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source_root / relative_path).read_bytes())
    evidence["scope_content_hashes"] = {
        relative_path: hashlib.sha256((tmp_path / relative_path).read_bytes()).hexdigest()
        for relative_path in evidence["scope_files"]
    }
    mutate(evidence)
    artifact = tmp_path / "evidence.json"
    artifact.write_text(json.dumps(evidence), encoding="utf-8")
    artifact.with_suffix(".sha256").write_text(hashlib.sha256(artifact.read_bytes()).hexdigest(), encoding="ascii")
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipeline.subprocess, "check_output", lambda *args, **kwargs: evidence["repo_commit"] + "\n")


@pytest.mark.parametrize("mutation,match", [
    (lambda evidence: evidence["relationships"].update({"bad": []}), "relationship schema"),
    (lambda evidence: next(iter(evidence["relationships"].values()))["callees_of"].update(files="bad"), "relationship schema"),
    (lambda evidence: next(iter(evidence["relationships"].values()))["callees_of"].update(result_count=-1), "relationship schema"),
    (lambda evidence: next(iter(evidence["relationships"].values()))["callees_of"].update(summary=None), "relationship schema"),
    (lambda evidence: evidence["dependencies"]["scripts/sod_pipeline.py"]["imports"].update(files="bad"), "dependency schema"),
    (lambda evidence: evidence["dependencies"]["scripts/sod_pipeline.py"]["imports"].update(result_count=-1), "dependency schema"),
    (lambda evidence: evidence["dependencies"]["scripts/sod_pipeline.py"]["imports"].update(summary=None), "dependency schema"),
    (lambda evidence: evidence["impact_query"].update(protocol={}), "query (schema|completeness) mismatch"),
    (lambda evidence: evidence["impact_query"].update(protocol=""), "query (schema|completeness) mismatch"),
    (lambda evidence: evidence["affected_files"]["scripts/sod_pipeline.py"].update(result_count=999), "affected file binding"),
], ids=["relationship_extra", "relationship_files", "relationship_count", "relationship_summary", "dependency_files", "dependency_count", "dependency_summary", "protocol_dict", "protocol_empty", "affected_count"])
def test_verify_graph_evidence_rejects_all_f009_nested_schema_mutations(tmp_path, monkeypatch, mutation, match):
    _mutated_graph_evidence(tmp_path, monkeypatch, mutation)
    with pytest.raises(RuntimeError, match=match):
        pipeline.verify_graph_evidence("evidence.json")


def test_l3_dispatch_passes_both_models_without_shell_interpolation(monkeypatch):
    args = pipeline.parse_args([
        "worker", "auditor", "GATE", "slug", "task; exit 9", "file.py",
        "--model", "lead/model", "--subagent-model", "worker/model",
    ])
    seen = []
    monkeypatch.setattr(pipeline, "capture", lambda command: (seen.append(command) or (0, "L3_SESSION_ID=s\nL3_ROLE_ID=21\nL3_ROLE_NAME=auditor\nL2_ROLE_ID=11\nL2_ROLE_NAME=worker\nMODEL=m\nSUBAGENT_MODEL=w\nRISK=high\nREPORT=x.md\nGATE=GATE\n---COMMAND---\nrun")))
    pipeline._dispatch_l3(args, "session")
    assert seen[0][-4:] == ["--model", "lead/model", "--subagent-model", "worker/model"]
    assert "task; exit 9" not in seen[0]


def test_main_remediates_once_then_enforces(monkeypatch, tmp_path):
    calls = []
    reports = iter(["[NEEDS_FIX] F-001: repair", "[APPROVED]"])
    monkeypatch.setattr(pipeline, "_dispatch_l2", lambda args, task: ({"SESSION_ID": "session", "ROLE_ID": "11"}, "run"))
    def dispatch_l3(args, session):
        return {"REPORT": "report.md"}, "run"

    def run(command, desc, check=True):
        calls.append((command, desc))
        if desc.startswith("L3"):
            report.write_text(next(reports), encoding="utf-8")
        return 0

    monkeypatch.setattr(pipeline, "_dispatch_l3", dispatch_l3)
    monkeypatch.setattr(pipeline, "capture", lambda command: (0, "PRE_AUDIT_PATH=x\nPRE_AUDIT_SHA256=" + "a" * 64))
    monkeypatch.setattr(pipeline, "run", run)
    report = tmp_path / "report.md"
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    assert pipeline.main(["worker", "auditor", "GATE", "slug", "task", "file.py", "--max-remediations", "1"]) == 0
    assert any("extract_lessons.py" in str(command) for command, _ in calls)
    assert any("sod_gate_enforcer.py" in str(command) for command, _ in calls)


def test_pre_audit_failure_never_falls_back_to_legacy_validation(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "_dispatch_l2", lambda args, task: ({"SESSION_ID": "s", "ROLE_ID": "11"}, "run"))
    calls = []
    monkeypatch.setattr(pipeline, "capture", lambda command: (1, "ANTI_DRIP[E105] failed"))
    monkeypatch.setattr(pipeline, "run", lambda command, desc, check=True: calls.append((command, desc)) or 0)
    assert pipeline.main(["worker", "auditor", "GATE", "slug", "task", "file.py", "--max-remediations", "0"]) == 1
    assert not any("Pre-L3 Validation" in desc or "L3 Codex Audit" in desc for _, desc in calls)


def test_validation_output_is_redacted(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "_dispatch_l2", lambda args, task: ({"SESSION_ID": "s", "ROLE_ID": "11"}, "run"))
    monkeypatch.setattr(pipeline, "capture", lambda command: (1, "Bearer top-secret"))
    monkeypatch.setattr(pipeline, "run", lambda *args, **kwargs: 0)
    assert pipeline.main(["worker", "auditor", "GATE", "slug", "task", "file.py", "--max-remediations", "0"]) == 1
    assert "top-secret" not in capsys.readouterr().out


def test_main_rejects_approved_stale_report_after_l3_failure(monkeypatch, tmp_path):
    report = tmp_path / "report.md"
    report.write_text("[APPROVED]", encoding="utf-8")
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "_dispatch_l2", lambda args, task: ({"SESSION_ID": "s", "ROLE_ID": "11"}, "run"))
    monkeypatch.setattr(pipeline, "_dispatch_l3", lambda args, session: ({"REPORT": "report.md"}, "run"))
    calls = []

    def run(command, desc, check=True):
        calls.append((command, desc))
        return 9 if desc.startswith("L3") else 0

    monkeypatch.setattr(pipeline, "run", run)
    assert pipeline.main(["worker", "auditor", "GATE", "slug", "task", "file.py", "--max-remediations", "0"]) == 2
    assert not any("sod_gate_enforcer.py" in str(command) for command, _ in calls)
    assert any("extract_lessons.py" in str(command) for command, _ in calls)


def test_main_rejects_stale_approved_report_when_l3_succeeds_without_writing(monkeypatch, tmp_path):
    report = tmp_path / "report.md"
    report.write_text("[APPROVED]", encoding="utf-8")
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "_dispatch_l2", lambda args, task: ({"SESSION_ID": "s", "ROLE_ID": "11"}, "run"))
    monkeypatch.setattr(pipeline, "_dispatch_l3", lambda args, session: ({"REPORT": "report.md"}, "run"))
    calls = []
    monkeypatch.setattr(pipeline, "run", lambda command, desc, check=True: calls.append((command, desc)) or 0)
    assert pipeline.main(["worker", "auditor", "GATE", "slug", "task", "file.py", "--max-remediations", "0"]) == 2
    assert not any("sod_gate_enforcer.py" in str(command) for command, _ in calls)


def test_main_rejects_report_that_was_unreadable_before_l3(monkeypatch, tmp_path):
    report = tmp_path / "report.md"
    report.write_bytes(b"\xff")
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "_dispatch_l2", lambda args, task: ({"SESSION_ID": "s", "ROLE_ID": "11"}, "run"))
    monkeypatch.setattr(pipeline, "_dispatch_l3", lambda args, session: ({"REPORT": "report.md"}, "run"))
    calls = []

    def run(command, desc, check=True):
        calls.append((command, desc))
        if desc.startswith("L3"):
            report.write_text("[APPROVED]", encoding="utf-8")
        return 0

    monkeypatch.setattr(pipeline, "run", run)
    assert pipeline.main(["worker", "auditor", "GATE", "slug", "task", "file.py", "--max-remediations", "0"]) == 2
    assert not any("sod_gate_enforcer.py" in str(command) for command, _ in calls)


@pytest.mark.parametrize("error", [PermissionError("locked"), UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte")])
def test_extract_findings_unreadable_report_fails_closed(monkeypatch, tmp_path, error):
    report = tmp_path / "report.md"
    report.write_text("F-001: stale", encoding="utf-8")
    monkeypatch.setattr(pipeline.Path, "read_text", lambda self, **kwargs: (_ for _ in ()).throw(error))
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    assert pipeline.extract_findings("report.md") == "Address all L3 audit findings and regressions."


@pytest.mark.parametrize("report_setup", ["missing", "directory"])
def test_main_missing_or_unreadable_report_fails_closed(monkeypatch, tmp_path, report_setup):
    report = tmp_path / "report.md"
    if report_setup == "directory":
        report.mkdir()
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "_dispatch_l2", lambda args, task: ({"SESSION_ID": "s", "ROLE_ID": "11"}, "run"))
    monkeypatch.setattr(pipeline, "_dispatch_l3", lambda args, session: ({"REPORT": "report.md"}, "run"))
    calls = []
    monkeypatch.setattr(pipeline, "run", lambda command, desc, check=True: calls.append((command, desc)) or 0)
    assert pipeline.main(["worker", "auditor", "GATE", "slug", "task", "file.py", "--max-remediations", "0"]) == 2
    assert any("extract_lessons.py" in str(command) for command, _ in calls)
    assert not any("sod_gate_enforcer.py" in str(command) for command, _ in calls)


def test_main_report_path_traversal_fails_closed(monkeypatch, tmp_path):
    outside = tmp_path.parent / "report.md"
    outside.write_text("[APPROVED]", encoding="utf-8")
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "_dispatch_l2", lambda args, task: ({"SESSION_ID": "s", "ROLE_ID": "11"}, "run"))
    monkeypatch.setattr(pipeline, "_dispatch_l3", lambda args, session: ({"REPORT": "../report.md"}, "run"))
    calls = []
    monkeypatch.setattr(pipeline, "run", lambda command, desc, check=True: calls.append((command, desc)) or 0)
    assert pipeline.main(["worker", "auditor", "GATE", "slug", "task", "file.py", "--max-remediations", "0"]) == 2
    assert not any("sod_gate_enforcer.py" in str(command) for command, _ in calls)


def test_main_runs_lesson_extraction_when_budget_is_zero(monkeypatch, tmp_path):
    report = tmp_path / "report.md"
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "_dispatch_l2", lambda args, task: ({"SESSION_ID": "s", "ROLE_ID": "11"}, "run"))
    monkeypatch.setattr(pipeline, "_dispatch_l3", lambda args, session: ({"REPORT": "report.md"}, "run"))
    calls = []

    def run(command, desc, check=True):
        calls.append((command, desc))
        if desc.startswith("L3"):
            report.write_text("[NEEDS_FIX] F-001", encoding="utf-8")
        return 0

    monkeypatch.setattr(pipeline, "run", run)
    assert pipeline.main(["worker", "auditor", "GATE", "slug", "task", "file.py", "--max-remediations", "0"]) == 2
    assert [desc for _, desc in calls].count("Lesson Extraction Hard Gate") == 1


@pytest.mark.skipif(shutil.which("powershell") is None, reason="Windows PowerShell is required for subprocess boundary tests")
def test_run_powershell_cleanup_oserror_does_not_mask_result(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    original_unlink = pipeline.Path.unlink

    def fail_cleanup(path, missing_ok=False):
        if path.name.startswith("_pipeline_step_"):
            raise PermissionError("locked")
        return original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(pipeline.Path, "unlink", fail_cleanup)
    assert pipeline.run("if ($true) { exit 7 }", "fault", check=False) == 7


def _owned_planning_lock(tmp_path):
    lock = tmp_path / ".implementation_plan.md.lock"
    owner = b"owner-a"
    lock.write_bytes(owner)
    return lock, lock.lstat(), owner


def _exclusive_planning_reacquisition(lock):
    fd = pipeline.os.open(lock, pipeline.os.O_CREAT | pipeline.os.O_EXCL | pipeline.os.O_WRONLY)
    try:
        assert pipeline.os.write(fd, b"new-live-owner") == len(b"new-live-owner")
        pipeline.os.fsync(fd)
        return pipeline.os.fstat(fd)
    finally:
        pipeline.os.close(fd)


def test_release_planning_lock_l3_raced_lstat_replacement_survives(tmp_path, monkeypatch):
    lock, identity, owner = _owned_planning_lock(tmp_path)
    replacement = tmp_path / "replacement.lock"
    replacement.write_bytes(b"foreign-owner")
    replacement_identity = replacement.lstat()
    assert identity.st_ino != replacement_identity.st_ino
    real_lstat, calls = Path.lstat, 0

    def raced_lstat(path, *args, **kwargs):
        nonlocal calls
        observed = real_lstat(path, *args, **kwargs)
        if path == lock:
            calls += 1
            if calls == 2:
                pipeline.os.replace(replacement, lock)
        return observed

    monkeypatch.setattr(Path, "lstat", raced_lstat)
    pipeline._release_planning_lock(lock, identity, owner)
    assert calls == 2
    assert lock.read_bytes() == b"foreign-owner", "release_race: deleted foreign lock"
    assert lock.stat().st_ino == replacement_identity.st_ino
    assert not replacement.exists() and not list(tmp_path.glob("*.trash"))


@pytest.mark.parametrize("replacement", ["identity", "owner", "owner-prefix"],
                         ids=["identity", "owner", "owner-prefix"])
@pytest.mark.parametrize("reacquire", ["vacant", "after-capture", "before-restore"])
def test_release_planning_lock_verifies_atomically_captured_lock(replacement, reacquire, tmp_path, monkeypatch):
    lock, identity, owner = _owned_planning_lock(tmp_path)
    sibling = tmp_path / "replacement.lock"
    sibling.write_bytes(owner)
    sibling_identity = sibling.stat()
    assert sibling_identity.st_ino != identity.st_ino
    real_replace, real_link = pipeline.os.replace, pipeline.os.link
    moves, newer = [], []

    def replace_before_capture(source, target):
        if source == lock:
            if replacement == "identity":
                real_replace(sibling, lock)
            else:
                lock.write_bytes(b"foreign-owner" if replacement == "owner" else owner + b"x")
        moves.append((source, target))
        real_replace(source, target)
        if reacquire == "after-capture":
            newer.append(_exclusive_planning_reacquisition(lock))

    def restore(source, target):
        moves.append((source, target))
        if reacquire == "before-restore":
            newer.append(_exclusive_planning_reacquisition(lock))
        real_link(source, target)

    monkeypatch.setattr(pipeline.os, "replace", replace_before_capture)
    monkeypatch.setattr(pipeline.os, "link", restore)
    if reacquire == "vacant":
        pipeline._release_planning_lock(lock, identity, owner)
    else:
        with pytest.raises(FileExistsError):
            pipeline._release_planning_lock(lock, identity, owner)
    assert len(moves) == 2 and moves[1] == (moves[0][1], lock)
    trash = moves[0][1]
    assert trash.parent == lock.parent and trash.suffix == ".trash"
    captured_bytes = owner if replacement == "identity" else b"foreign-owner" if replacement == "owner" else owner + b"x"
    if newer:
        assert lock.read_bytes() == b"new-live-owner"
        assert (lock.stat().st_dev, lock.stat().st_ino) == (newer[0].st_dev, newer[0].st_ino)
        assert trash.read_bytes() == captured_bytes
        captured_identity = sibling_identity if replacement == "identity" else identity
        assert (trash.stat().st_dev, trash.stat().st_ino) == (captured_identity.st_dev, captured_identity.st_ino)
        return
    assert lock.read_bytes() == captured_bytes
    assert lock.stat().st_ino != identity.st_ino if replacement == "identity" else lock.stat().st_ino == identity.st_ino
    assert not trash.exists()


def test_release_planning_lock_preserves_new_owner_after_capture(tmp_path, monkeypatch):
    lock, identity, owner = _owned_planning_lock(tmp_path)
    real_replace = pipeline.os.replace
    moves = []

    def new_owner_after_capture(source, target):
        assert source == lock and target.parent == lock.parent
        real_replace(source, target)
        moves.append(target)
        lock.write_bytes(b"new-owner")

    monkeypatch.setattr(pipeline.os, "replace", new_owner_after_capture)
    pipeline._release_planning_lock(lock, identity, owner)
    assert len(moves) == 1 and not moves[0].exists()
    assert lock.read_bytes() == b"new-owner"
    assert lock.stat().st_ino != identity.st_ino


@pytest.mark.parametrize("fault", ["missing", "capture-oserror"], ids=["missing", "capture-oserror"])
def test_release_planning_lock_capture_failure_preserves_owner(fault, tmp_path, monkeypatch):
    lock, identity, owner = _owned_planning_lock(tmp_path)

    def fail_replace(source, target):
        if fault == "missing":
            source.unlink()
            raise FileNotFoundError("lock vanished")
        raise PermissionError("capture denied")

    monkeypatch.setattr(pipeline.os, "replace", fail_replace)
    if fault == "missing":
        pipeline._release_planning_lock(lock, identity, owner)
        assert not lock.exists()
    else:
        with pytest.raises(PermissionError, match="capture denied"):
            pipeline._release_planning_lock(lock, identity, owner)
        assert lock.read_bytes() == owner
    assert not list(tmp_path.glob("*.trash"))


@pytest.mark.parametrize("fault", ["lstat", "open", "fstat", "read", "close", "unlink", "missing-open", "missing-unlink"],
                         ids=["lstat", "open", "fstat", "read", "close", "unlink", "missing-open", "missing-unlink"])
@pytest.mark.parametrize("reacquire", ["vacant", "after-capture", "before-restore"])
def test_release_planning_lock_post_capture_error_restores_owner(fault, reacquire, tmp_path, monkeypatch):
    lock, identity, owner = _owned_planning_lock(tmp_path)
    real_lstat, real_open, real_unlink, real_fstat = Path.lstat, Path.open, Path.unlink, pipeline.os.fstat
    real_replace, real_link = pipeline.os.replace, pipeline.os.link
    reads, failed, descriptors = [], [], []
    captured, newer = [], []

    def capture(source, target):
        real_replace(source, target)
        captured.append(target)
        if reacquire == "after-capture":
            newer.append(_exclusive_planning_reacquisition(lock))

    def restore(source, target):
        if reacquire == "before-restore":
            newer.append(_exclusive_planning_reacquisition(lock))
        real_link(source, target)

    def fail():
        failed.append(fault)
        error = FileNotFoundError if fault.startswith("missing-") else PermissionError
        raise error("captured lock fault")

    def trash_lstat(path, *args, **kwargs):
        if path.suffix == ".trash" and fault == "lstat" and not failed:
            fail()
        return real_lstat(path, *args, **kwargs)

    class FaultyReader:
        def __init__(self, handle):
            self.handle = handle
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            self.handle.close()
            if fault == "close":
                fail()
        def fileno(self):
            return self.handle.fileno()
        def read(self, size):
            reads.append(size)
            assert size == len(owner) + 1
            if fault == "read":
                fail()
            return self.handle.read(size)

    def trash_open(path, *args, **kwargs):
        if path.suffix == ".trash":
            if fault in {"open", "missing-open"}:
                fail()
            handle = real_open(path, *args, **kwargs)
            descriptors.append(handle.fileno())
            return FaultyReader(handle)
        return real_open(path, *args, **kwargs)

    def trash_fstat(fd):
        if fault == "fstat" and fd in descriptors and not failed:
            fail()
        return real_fstat(fd)

    def trash_unlink(path, *args, **kwargs):
        if path.suffix == ".trash" and fault in {"unlink", "missing-unlink"} and not failed:
            fail()
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", trash_lstat)
    monkeypatch.setattr(Path, "open", trash_open)
    monkeypatch.setattr(Path, "unlink", trash_unlink)
    monkeypatch.setattr(pipeline.os, "fstat", trash_fstat)
    monkeypatch.setattr(pipeline.os, "replace", capture)
    monkeypatch.setattr(pipeline.os, "link", restore)
    with pytest.raises(OSError, match="captured lock fault" if reacquire == "vacant" else None):
        pipeline._release_planning_lock(lock, identity, owner)
    assert failed == [fault]
    assert lock.read_bytes() == (b"new-live-owner" if newer else owner)
    expected = newer[0] if newer else identity
    assert (lock.stat().st_dev, lock.stat().st_ino) == (expected.st_dev, expected.st_ino)
    assert reads == ([len(owner) + 1] if fault in {"read", "close", "unlink", "missing-unlink"} else [])
    if newer:
        with real_open(captured[0], "rb") as handle:
            assert handle.read() == owner
        assert (real_lstat(captured[0]).st_dev, real_lstat(captured[0]).st_ino) == (identity.st_dev, identity.st_ino)
    else:
        assert not list(tmp_path.glob("*.trash"))


@pytest.mark.parametrize("reacquire", ["vacant", "after-capture", "before-restore"])
def test_release_planning_lock_opened_identity_mismatch_restores_owner(reacquire, tmp_path, monkeypatch):
    from types import SimpleNamespace

    lock, identity, owner = _owned_planning_lock(tmp_path)
    real_replace, real_link, real_fstat = pipeline.os.replace, pipeline.os.link, pipeline.os.fstat
    captured, newer = [], []

    def capture(source, target):
        real_replace(source, target)
        captured.append(target)
        if reacquire == "after-capture":
            newer.append(_exclusive_planning_reacquisition(lock))

    def restore(source, target):
        if reacquire == "before-restore":
            newer.append(_exclusive_planning_reacquisition(lock))
        real_link(source, target)

    def changed_fstat(fd):
        observed = real_fstat(fd)
        return SimpleNamespace(st_dev=observed.st_dev, st_ino=observed.st_ino + 1) if captured and observed.st_ino == identity.st_ino else observed

    monkeypatch.setattr(pipeline.os, "replace", capture)
    monkeypatch.setattr(pipeline.os, "link", restore)
    monkeypatch.setattr(pipeline.os, "fstat", changed_fstat)
    if reacquire == "vacant":
        pipeline._release_planning_lock(lock, identity, owner)
        assert lock.read_bytes() == owner and lock.stat().st_ino == identity.st_ino
        assert not list(tmp_path.glob("*.trash"))
    else:
        with pytest.raises(FileExistsError):
            pipeline._release_planning_lock(lock, identity, owner)
        assert lock.read_bytes() == b"new-live-owner"
        assert (lock.stat().st_dev, lock.stat().st_ino) == (newer[0].st_dev, newer[0].st_ino)
        assert captured[0].read_bytes() == owner and captured[0].stat().st_ino == identity.st_ino
    assert len(captured) == 1


@pytest.mark.parametrize("fault", ["mismatch", "verification-error"], ids=["mismatch", "verification-error"])
def test_release_planning_lock_failed_restore_retains_captured_lock(fault, tmp_path, monkeypatch):
    lock, identity, owner = _owned_planning_lock(tmp_path)
    real_replace, real_open = pipeline.os.replace, Path.open
    captured = []

    def capture(source, target):
        if fault == "mismatch":
            lock.write_bytes(b"foreign-owner")
        real_replace(source, target)
        captured.append(target)

    def fail_restore(source, target):
        assert source == captured[0] and target == lock
        raise PermissionError("restore denied")

    def fail_verification(path, *args, **kwargs):
        if path.suffix == ".trash" and fault == "verification-error":
            raise PermissionError("verification denied")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(pipeline.os, "replace", capture)
    monkeypatch.setattr(pipeline.os, "link", fail_restore)
    monkeypatch.setattr(Path, "open", fail_verification)
    with pytest.raises(PermissionError, match="restore denied"):
        pipeline._release_planning_lock(lock, identity, owner)
    assert len(captured) == 1 and not lock.exists()
    with real_open(captured[0], "rb") as handle:
        assert handle.read() == (b"foreign-owner" if fault == "mismatch" else owner)
    assert captured[0].stat().st_ino == identity.st_ino


@pytest.mark.parametrize("fault", ["mismatch", "verification-error"])
def test_release_planning_lock_occupied_directory_retains_evidence(fault, tmp_path, monkeypatch):
    lock, identity, owner = _owned_planning_lock(tmp_path)
    real_replace, real_open = pipeline.os.replace, Path.open
    captured = []

    def capture(source, target):
        if fault == "mismatch":
            lock.write_bytes(b"foreign-owner")
        real_replace(source, target)
        captured.append(target)
        lock.mkdir()

    def verify(path, *args, **kwargs):
        if path.suffix == ".trash" and fault == "verification-error":
            raise PermissionError("verification denied")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(pipeline.os, "replace", capture)
    monkeypatch.setattr(Path, "open", verify)
    with pytest.raises(OSError):
        pipeline._release_planning_lock(lock, identity, owner)
    assert lock.is_dir()
    with real_open(captured[0], "rb") as handle:
        assert handle.read() == (b"foreign-owner" if fault == "mismatch" else owner)
    assert captured[0].stat().st_ino == identity.st_ino


@pytest.mark.parametrize("fault", ["mismatch", "verification-error"])
def test_release_planning_lock_restore_cleanup_error_retains_both_entries(fault, tmp_path, monkeypatch):
    lock, identity, owner = _owned_planning_lock(tmp_path)
    real_replace, real_open, real_unlink = pipeline.os.replace, Path.open, Path.unlink
    captured = []

    def capture(source, target):
        if fault == "mismatch":
            lock.write_bytes(b"foreign-owner")
        real_replace(source, target)
        captured.append(target)

    def verify(path, *args, **kwargs):
        if path.suffix == ".trash" and fault == "verification-error":
            raise PermissionError("verification denied")
        return real_open(path, *args, **kwargs)

    def cleanup(path, *args, **kwargs):
        if path.suffix == ".trash":
            raise PermissionError("restore cleanup denied")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(pipeline.os, "replace", capture)
    monkeypatch.setattr(Path, "open", verify)
    monkeypatch.setattr(Path, "unlink", cleanup)
    with pytest.raises(PermissionError, match="restore cleanup denied"):
        pipeline._release_planning_lock(lock, identity, owner)
    expected = b"foreign-owner" if fault == "mismatch" else owner
    assert lock.read_bytes() == expected
    with real_open(captured[0], "rb") as handle:
        assert handle.read() == expected
    assert lock.stat().st_ino == captured[0].stat().st_ino == identity.st_ino


def test_release_planning_lock_without_identity_or_path_is_harmless(tmp_path, monkeypatch):
    lock, identity, owner = _owned_planning_lock(tmp_path)
    pipeline._release_planning_lock(lock, None, owner)
    assert lock.read_bytes() == owner
    lock.unlink()
    pipeline._release_planning_lock(lock, identity, owner)
    assert not lock.exists()


def test_release_planning_lock_owned_trash_names_are_unique(tmp_path, monkeypatch):
    real_replace = pipeline.os.replace
    captured = []

    def capture(source, target):
        assert source != target and source.parent == target.parent
        assert target.suffix == ".trash" and not target.exists()
        real_replace(source, target)
        captured.append(target)

    monkeypatch.setattr(pipeline.os, "replace", capture)
    for _ in range(2):
        lock, identity, owner = _owned_planning_lock(tmp_path)
        pipeline._release_planning_lock(lock, identity, owner)
        assert not lock.exists()
    assert len(set(captured)) == 2 and not list(tmp_path.glob("*.trash"))


def test_release_planning_lock_missing_captured_trash_fails_closed(tmp_path, monkeypatch):
    lock, identity, owner = _owned_planning_lock(tmp_path)
    real_replace = pipeline.os.replace

    def remove_captured_trash(source, target):
        real_replace(source, target)
        target.unlink()

    monkeypatch.setattr(pipeline.os, "replace", remove_captured_trash)
    with pytest.raises(FileNotFoundError):
        pipeline._release_planning_lock(lock, identity, owner)
    assert not lock.exists() and not list(tmp_path.glob("*.trash"))
