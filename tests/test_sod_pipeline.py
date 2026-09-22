import hashlib
import json
import shutil
from pathlib import Path

import pytest

import scripts.sod_pipeline as pipeline

GRAPH_ARTIFACT = ".ly_state/session/graph_evidence_l2_role11_sod_pipeline_standardization_20260922.json"


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
    monkeypatch.setattr(pipeline, "run", run)
    report = tmp_path / "report.md"
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    assert pipeline.main(["worker", "auditor", "GATE", "slug", "task", "file.py", "--max-remediations", "1"]) == 0
    assert any("extract_lessons.py" in str(command) for command, _ in calls)
    assert any("sod_gate_enforcer.py" in str(command) for command, _ in calls)


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
