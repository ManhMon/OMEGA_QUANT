"""Documentation regression checks; no alpha implementation or gate approval."""

from pathlib import Path
import hashlib
import re
import shlex
import subprocess
import sys

import pytest


PLAN = Path(__file__).resolve().parents[1] / ".ly_state/session/master_plan_news_sentiment_macro_alpha_20261020.md"
PREPARATION = "P3 graph-input preparation may proceed after its P1 inputs exist, but does not complete P3."
ACCEPTANCE = "P3 acceptance requires P1 completion and successful P2 exit checks before validating one-hop innovations and direct/sector/randomized graph ablations."
INDEPENDENCE = "P4 and P5 can proceed independently after their own P1 inputs exist"
EXCLUSION = "P6 may evaluate a reduced baseline but must name excluded workstreams and cannot claim complete four-stream delivery."
DEPENDENCIES = {
    "P0": "None", "P1": "P0", "P2": "P1", "P3": "P1, P2",
    "P4": "P1", "P5": "P1",
    "P6": "P2–P5, or documented exclusion of optional stream", "P7": "P6",
}


SCORER = "TypeSafe JEV Scorer & Swappable Model Registry"
SECTION_CONTRACTS = {
    "P0 — historical inventory reconciliation (F-003)": (
        "Historical W0 inventory drift reconciliation is a blocking Package P0 deliverable, not a planning-gate prerequisite.",
        "P0 cannot complete and P1 cannot start until independently traceable source reconciliation and the original inventory regression pass.",
        "tests/test_sod_jev_model_routing.py::test_w0_inventory_binds_sources_consumers_and_market_release",
        "do not delete, skip or weaken its assertions",
        "Do not guess counts/hashes or overwrite datasets/manifests",
        "F-003 data reconciliation remains OPEN",
    ),
    f"P1 — {SCORER}": (
        "JEV dispatch/advisor routing is not financial sentiment inference.",
        "any choice-to-score mapping must be explicit, versioned and training-calibrated",
        "every cache hit revalidates the same schema, lineage, registry eligibility and readiness gates as a fresh result",
        "signed score [-1,1], confidence and attribution [0,1] must be finite, never booleans or coerced strings",
        "explicit unavailable/error states carry reason codes, not a fabricated neutral score",
        "immutable model revisions and artifact digests",
        "reject unknown/disabled IDs, duplicate entries, incompatible schemas and digest mismatches",
        "Resolve one immutable registry snapshot per run",
        "a swap starts a new run/version, never mutates in-flight or historical scores",
        "Cache/replay keys bind input, model, prompt, schema, preprocessing, calibration and registry digests",
        "No silent provider/model fallback",
        "unknown training cutoff remains retrospective-only",
        "available_at = max(source_available_at, score_ready_at, model_available_at, calibration_available_at)",
        "as_of <= available_at <= decision_time plus the next eligible trading-session lag",
        "inclusive 15:30 ICT batch cutoff",
        "missing readiness or caller-supplied provenance claims fail closed",
    ),
    f"P2 — {SCORER} validation": (
        "frozen lexicon baseline on independently labeled Vietnamese issuer/event samples",
        "calibration and model selection use training/validation only, never the untouched OOS interval",
        "distinct lineage/cache identities and unchanged historical outputs",
        "numerical equality across different models is not required",
        "NaN/Inf/-Inf, overflow, zero/negative normalization denominators",
        "provider timeout/429 exhaustion, unauthorized fallback, future timestamps and cutoff equality/+one-unit cases",
        "rejected results cannot publish scores, unavailable is not valid_no_news",
        "documentation tests do not implement or certify them",
    ),
}
PLANNING_SCOPE = "Planning-gate verification is limited to tests/test_master_plan_news_sentiment_macro_alpha.py."
INVENTORY_SCOPE = "Historical W0 inventory checks are excluded from planning-gate execution and retained as mandatory P0 acceptance evidence."


def section_once(text, heading, level):
    matches = re.findall(rf"(?ms)^{level} {re.escape(heading)}\n(.*?)(?=^#{{1,{len(level)}}} |\Z)", text)
    if len(matches) != 1:
        raise ValueError(f"missing or duplicate section: {heading}")
    return matches[0]


def validate_plan(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("plan must be nonempty text")
    sections = re.findall(
        r"(?ms)^## 10\. Delivery sequence, ownership and measurable exits\n(.*?)^## 11\. ", text
    )
    if len(sections) != 1:
        raise ValueError("delivery section must occur once")
    section = sections[0]
    for package, dependency in DEPENDENCIES.items():
        rows = re.findall(rf"(?m)^\| {package} — [^\n]+$", section)
        if len(rows) != 1 or len(rows[0].split("|")) != 6 or rows[0].split("|")[3].strip() != dependency:
            raise ValueError(f"{package} dependency mismatch")
    if re.findall(r"(?m)^\| (P\S*) — ", section) != list(DEPENDENCIES):
        raise ValueError("packages must remain in dependency order")
    for clause in (PREPARATION, ACCEPTANCE, INDEPENDENCE, EXCLUSION):
        if section.count(clause) != 1:
            raise ValueError("missing or duplicate scheduling contract")
    if "P3, P4 and P5 can proceed independently" in section:
        raise ValueError("P1-only P3 completion is forbidden")
    for package, marker in (("P0", "Historical W0 inventory drift reconciliation (F-003)"), ("P1", SCORER), ("P2", SCORER)):
        row = re.search(rf"(?m)^\| {package} — [^\n]+$", section).group()
        if marker not in row.split("|")[4]:
            raise ValueError(f"{package} deliverable missing")
    for heading, clauses in SECTION_CONTRACTS.items():
        body = section_once(section, heading, "###")
        if section_once(text, heading, "###") != body:
            raise ValueError("contract section outside delivery scope")
        for clause in clauses:
            if body.count(clause) != 1:
                raise ValueError(f"missing or duplicate contract in {heading}")
    verification = section_once(text, "11. Verification contract and 24-dimension adversarial matrix", "##")
    for clause in (PLANNING_SCOPE, INVENTORY_SCOPE):
        if verification.count(clause) != 1:
            raise ValueError("planning/inventory verification scope mismatch")
    commands = re.findall(r"(?m)^pytest [^\n]+$", verification)
    if len(commands) != 3 or sum("--collect-only" in command for command in commands) != 1:
        raise ValueError("collect/focused/full planning commands required")
    for command, phase in zip(commands, ("collect", "focused", "test")):
        expected = ["pytest"] + (["--collect-only"] if phase == "collect" else [])
        expected += ["-o", "addopts=", "--capture=sys", "-p", "no:terminal", f"--junitxml=.ly_state/session/<implementation_session>_{phase}.xml", "tests/test_master_plan_news_sentiment_macro_alpha.py"]
        if shlex.split(command) != expected:
            raise ValueError("planning verification command mismatch")


def test_f001_delivery_dependencies_are_consistent():
    validate_plan(PLAN.read_text(encoding="utf-8"))


def test_f001_p1_only_completion_is_rejected():
    text = PLAN.read_text(encoding="utf-8")
    legacy = "P3, P4 and P5 can proceed independently after their own P1 inputs exist; "
    for replacement in (legacy, "P3 acceptance requires only P1 completion. "):
        with pytest.raises(ValueError):
            validate_plan(text.replace(PREPARATION + " " + ACCEPTANCE + " ", replacement))


def test_f001_missing_or_reversed_dependencies_are_rejected():
    text = PLAN.read_text(encoding="utf-8")
    for dependency in ("P1", "P2", "None", "P2, P1", "P1, P2 or optional exclusion"):
        with pytest.raises(ValueError):
            validate_plan(text.replace("| P1, P2 |", f"| {dependency} |"))


def test_f001_missing_or_failed_p2_exit_is_not_acceptance():
    text = PLAN.read_text(encoding="utf-8")
    for replacement in ("P2 started", "failed P2 exit checks", "P2 exit checks", "P2 inputs exist"):
        with pytest.raises(ValueError):
            validate_plan(text.replace("successful P2 exit checks", replacement))
    with pytest.raises(ValueError):
        validate_plan(text.replace("P1 completion and successful P2", "successful P2"))
    with pytest.raises(ValueError):
        validate_plan(text.replace("but does not complete P3", "and completes P3"))


def test_f001_missing_duplicate_or_malformed_contract_is_rejected():
    text = PLAN.read_text(encoding="utf-8")
    for clause in (PREPARATION, ACCEPTANCE, INDEPENDENCE, EXCLUSION):
        for replacement in ("", clause + " " + clause):
            with pytest.raises(ValueError):
                validate_plan(text.replace(clause, replacement))
    for package in DEPENDENCIES:
        row = re.search(rf"(?m)^\| {package} — [^\n]+$", text).group()
        for replacement in ("", row + "\n" + row, row.replace("|", "", 1)):
            with pytest.raises(ValueError):
                validate_plan(text.replace(row, replacement))
    for replacement in ("## 10. Missing", "## 10. Delivery sequence, ownership and measurable exits\n## 11. Extra\n## 10. Delivery sequence, ownership and measurable exits"):
        with pytest.raises(ValueError):
            validate_plan(text.replace("## 10. Delivery sequence, ownership and measurable exits", replacement))


def test_f001_independence_and_exclusion_cannot_bypass_completion():
    text = PLAN.read_text(encoding="utf-8")
    for original, replacement in (
        (INDEPENDENCE, "P3, P4 and P5 can proceed independently after their own P1 inputs exist"),
        (EXCLUSION, "P6 may claim complete four-stream delivery with exclusions."),
        ("| P1, P2 |", "| P1, P2, or documented optional exclusion |"),
    ):
        with pytest.raises(ValueError):
            validate_plan(text.replace(original, replacement))


def test_f001_nontext_and_empty_inputs_fail_closed():
    for value in (None, "", " \n", True, [], {}, 0, -1, 10**13, float("nan"), float("inf"), -float("inf")):
        with pytest.raises(ValueError):
            validate_plan(value)


def test_f001_validator_exits_nonzero_without_mutating_input(tmp_path):
    source = PLAN.read_text(encoding="utf-8")
    for index, text in enumerate((source, source.replace(ACCEPTANCE, ""), "")):
        path = tmp_path / f"plan_{index}.md"
        path.write_text(text, encoding="utf-8", newline="\n")
        before = path.read_bytes()
        result = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).resolve()), str(path)],
            capture_output=True, text=True, timeout=30, check=False,
        )
        assert (result.returncode == 0) == (index == 0), result.stderr
        assert path.read_bytes() == before


def test_f001_scorer_registry_contracts_reject_missing_duplicate_or_moved_clauses():
    text = PLAN.read_text(encoding="utf-8")
    for heading, clauses in SECTION_CONTRACTS.items():
        header = f"### {heading}"
        for replacement in ("", header + "\n\n" + header):
            with pytest.raises(ValueError):
                validate_plan(text.replace(header, replacement))
        for clause in clauses:
            for replacement in ("", clause + " " + clause):
                mutated = text.replace(clause, replacement, 1)
                with pytest.raises(ValueError):
                    validate_plan(mutated)
            with pytest.raises(ValueError):
                validate_plan(text.replace(clause, "", 1) + "\n" + clause)


def test_f001_package_rows_cannot_omit_or_move_scorer_deliverables():
    text = PLAN.read_text(encoding="utf-8")
    for package, marker in (("P0", "Historical W0 inventory drift reconciliation (F-003)"), ("P1", SCORER), ("P2", SCORER)):
        row = re.search(rf"(?m)^\| {package} — [^\n]+$", text).group()
        for replacement in (row.replace(marker, ""), row.replace(marker, "").replace(package, package + " " + marker, 1)):
            with pytest.raises(ValueError):
                validate_plan(text.replace(row, replacement))


def test_f001_row_shape_order_and_global_contract_uniqueness():
    text = PLAN.read_text(encoding="utf-8")
    validate_plan(text)
    first = re.search(r"(?m)^\| P0 — [^\n]+$", text).group()
    second = re.search(r"(?m)^\| P1 — [^\n]+$", text).group()
    for mutation in (
        text.replace(first + "\n" + second, second + "\n" + first),
        text.replace(first, first.replace("|", "", 2)),
        text.replace(first, first + " extra |"),
        text.replace(second, second + "\n" + second.replace("P1", "P8", 1)),
        text.replace(second, second + "\n" + second.replace("P1", "P01", 1)),
        text + "\n### " + next(iter(SECTION_CONTRACTS)) + "\nDuplicate outside delivery\n",
    ):
        assert mutation != text
        with pytest.raises(ValueError):
            validate_plan(mutation)


def test_f003_inventory_remains_blocking_p0_not_planning_execution():
    text = PLAN.read_text(encoding="utf-8")
    validate_plan(text)
    for clause in (PLANNING_SCOPE, INVENTORY_SCOPE):
        for replacement in ("", clause + " " + clause, "W0 inventory reconciliation is waived."):
            with pytest.raises(ValueError):
                validate_plan(text.replace(clause, replacement))
    command = next(line for line in text.splitlines() if line.startswith("pytest --collect-only"))
    for replacement in (
        command + " tests/test_sod_jev_model_routing.py",
        command + " tests/test_update_market_data_resilience.py",
        command.replace("tests/test_master_plan_news_sentiment_macro_alpha.py", "tests"),
        command.replace("tests/test_master_plan_news_sentiment_macro_alpha.py", "tests/test_master_plan_news_sentiment_macro_alpha.py::test_f001_delivery_dependencies_are_consistent"),
        command.replace('--capture=sys', '--capture=fd'),
        command.replace('--collect-only ', ''),
        command + " -k nonexistent",
        command + " || true",
        command.replace('_collect.xml', '_test.xml'),
        "",
        command + "\n" + command,
    ):
        with pytest.raises(ValueError):
            validate_plan(text.replace(command, replacement))


def test_f001_cli_rejects_io_encoding_and_scorer_contract_failures(tmp_path):
    source = PLAN.read_text(encoding="utf-8")
    paths = [tmp_path / "missing.md", tmp_path]
    for index, raw in enumerate((b"\xff", b"\xef\xbb\xbf" + source.encode(), source.replace("\n", "\r\n").encode(), source.replace("No silent provider/model fallback", "Fallback allowed").encode(), source.replace("P0 cannot complete and P1 cannot start", "P0 may complete and P1 may start").encode())):
        path = tmp_path / f"bad_{index}.md"
        path.write_bytes(raw)
        paths.append(path)
    before = {path: path.read_bytes() for path in paths if path.is_file()}
    for path in paths:
        result = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).resolve()), str(path)],
            capture_output=True, text=True, timeout=30, check=False,
        )
        assert result.returncode != 0
    assert {path: path.read_bytes() for path in before} == before
    assert not paths[0].exists()


def run_formula_self_check(block):
    if hashlib.sha256(block.encode("utf-8")).hexdigest() != "22fdbe4c1a036b608d4423ef532d23c102a1dab0dd3d81050c7ea612489343b4":
        raise ValueError("formula example differs from reviewed code")
    exec(compile(block, str(PLAN), "exec"), {})


def test_f001_modified_formula_rejected_before_execution(tmp_path):
    marker = tmp_path / "unexpected"
    block = f"from pathlib import Path\nPath({str(marker)!r}).write_text('side effect')\n"
    with pytest.raises(ValueError):
        run_formula_self_check(block)
    assert not marker.exists()


def test_plan_encoding_and_formula_self_check():
    raw = PLAN.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw
    text = raw.decode("utf-8", errors="strict")
    blocks = re.findall(r"(?ms)^```python\n(.*?)^```", text)
    assert len(blocks) == 1
    run_formula_self_check(blocks[0])
    assert len(re.findall(r"(?m)^\| (?:[1-9]|1[0-9]|2[0-4]) \|", text)) == 24


if __name__ == "__main__":
    raw = Path(sys.argv[1]).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise ValueError("plan must be UTF-8 without BOM, with LF line endings")
    validate_plan(raw.decode("utf-8", errors="strict"))
