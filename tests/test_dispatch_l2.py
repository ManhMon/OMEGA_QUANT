import subprocess
import sys
import hashlib
import json
import os
from datetime import datetime
import pytest
from pathlib import Path
from scripts.dispatch_l2 import (
    parse_cli_args,
    infer_risk,
    parse_frontmatter,
    MODELS,
)
import scripts.dispatch_l2 as dispatch_l2

REPO_ROOT = Path(__file__).parent.parent


def _session_locks_cleanup_context():
    """Context manager implementation of lock cleanup for direct test verification."""
    created_locks = set()
    try:
        yield created_locks
    finally:
        for lock in created_locks:
            if isinstance(lock, Path):
                lock.unlink(missing_ok=True)
            elif isinstance(lock, str):
                Path(lock).unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _cleanup_session_locks():
    """Track and clean only lockfiles explicitly registered/created by the test case itself."""
    yield from _session_locks_cleanup_context()


def test_parse_cli_args_valid_positional_only():
    args = [
        "data-engineer",
        "TEST_GATE",
        "test_slug",
        "Test task description",
        "src/omega/data/",
    ]
    role, gate, slug, desc, scope, risk = parse_cli_args(args)
    assert role == "data-engineer"
    assert gate == "TEST_GATE"
    assert slug == "test_slug"
    assert desc == "Test task description"
    assert scope == "src/omega/data/"
    assert risk is None


def test_parse_cli_args_with_risk_flag():
    args = [
        "data-engineer",
        "TEST_GATE",
        "test_slug",
        "Test task description",
        "tests/fixtures/",
        "--risk",
        "low",
    ]
    role, gate, slug, desc, scope, risk = parse_cli_args(args)
    assert role == "data-engineer"
    assert risk == "low"


def test_parse_cli_args_with_risk_flag_high():
    args = [
        "--risk",
        "high",
        "data-engineer",
        "TEST_GATE",
        "test_slug",
        "Test task description",
        "src/",
    ]
    role, gate, slug, desc, scope, risk = parse_cli_args(args)
    assert role == "data-engineer"
    assert risk == "high"


def test_parse_cli_args_exit_2_on_duplicate_risk_flag():
    with pytest.raises(SystemExit) as excinfo:
        parse_cli_args(["data-engineer", "TEST_GATE", "slug", "desc", "scope", "--risk", "low", "--risk", "high"])
    assert excinfo.value.code == 2


def test_parse_cli_args_exit_2_on_invalid_risk_value():
    with pytest.raises(SystemExit) as excinfo:
        parse_cli_args(["data-engineer", "TEST_GATE", "slug", "desc", "scope", "--risk", "invalid"])
    assert excinfo.value.code == 2


def test_parse_cli_args_exit_2_on_missing_risk_value():
    with pytest.raises(SystemExit) as excinfo:
        parse_cli_args(["data-engineer", "TEST_GATE", "slug", "desc", "scope", "--risk"])
    assert excinfo.value.code == 2


def test_parse_cli_args_exit_2_on_invalid_flag():
    with pytest.raises(SystemExit) as excinfo:
        parse_cli_args(["data-engineer", "TEST_GATE", "slug", "desc", "scope", "--unknown"])
    assert excinfo.value.code == 2


def test_parse_cli_args_exit_2_on_insufficient_positional_args():
    with pytest.raises(SystemExit) as excinfo:
        parse_cli_args(["data-engineer", "TEST_GATE", "slug"])
    assert excinfo.value.code == 2


def test_infer_risk_high():
    risk, reason = infer_risk("src/omega/data/macro_pipeline.py")
    assert risk == "high"
    assert "macro_pipeline" in reason


def test_infer_risk_medium():
    risk, reason = infer_risk("src/omega/core/engine.py")
    assert risk == "medium"


def test_infer_risk_low():
    risk, reason = infer_risk("tests/fixtures/data.json")
    assert risk == "low"


def test_model_mapping():
    assert "high" in MODELS
    assert "medium" in MODELS
    assert "low" in MODELS
    for level in ("high", "medium", "low"):
        assert isinstance(MODELS[level], str)
        assert len(MODELS[level]) > 0
        assert MODELS[level] == "9router/cx/gpt-5.6-luna"


def test_parse_frontmatter():
    fm_text = """---
name: data-engineer
role_id: 15
tier: 2
platform: OpenCode
---
# Content"""
    fm = parse_frontmatter(fm_text)
    assert fm.get("name") == "data-engineer"
    assert fm.get("role_id") == 15
    assert fm.get("tier") == 2
    assert fm.get("platform") == "OpenCode"


def _parse_command_and_prompt(stdout: str) -> tuple[str, Path, str]:
    """Extract generated PS command, prompt temp-file path and its UTF-8 content."""
    command = stdout.split("---COMMAND---", 1)[1].strip()
    import re
    match = re.search(r"\[System\.IO\.File\]::ReadAllBytes\('(.+?)'\)", command)
    assert match, f"command must read prompt from UTF-8 temp file: {command}"
    prompt_path = Path(match.group(1))
    assert prompt_path.exists()
    return command, prompt_path, prompt_path.read_text(encoding="utf-8")


def test_dispatch_l2_cli_run_and_prompt_construction():
    res = subprocess.run(
        [
            sys.executable,
            "scripts/dispatch_l2.py",
            "data-engineer",
            "TEST_GATE_16DIM",
            "test_task_slug",
            "Execute adversarial matrix validation",
            "scripts/validate_l2_report.py",
            "--risk",
            "low",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert res.returncode == 0
    stdout = res.stdout

    assert "SESSION_ID=l2_role15_test_task_slug_" in stdout
    assert "ROLE_ID=15" in stdout
    assert "ROLE_NAME=data-engineer" in stdout
    assert "GATE=TEST_GATE_16DIM" in stdout
    assert "RISK=low (explicit --risk flag)" in stdout
    assert "---COMMAND---" in stdout

    command, prompt_path, prompt = _parse_command_and_prompt(stdout)
    assert '-m "9router/cx/gpt-5.6-luna"' in command

    # Prompt check: 16 dimensions
    assert "MANDATORY 16-DIMENSION ADVERSARIAL TESTING DIRECTIVE" in prompt
    for dim_num in range(1, 17):
        assert f"({dim_num})" in prompt

    # Prompt check: headings and format
    assert "## Summary" in prompt
    assert "## Repo-Local Files Read" in prompt
    assert "## Changes Made" in prompt
    assert "## Verification" in prompt
    assert "## Forbidden Path Scan" in prompt
    assert "non-authoritative scan evidence only; no reliance." in prompt


def test_dispatch_l2_cli_invalid_role_exit_2():
    res = subprocess.run(
        [
            sys.executable,
            "scripts/dispatch_l2.py",
            "nonexistent-role",
            "TEST_GATE",
            "slug",
            "desc",
            "scope",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert res.returncode == 2
    assert "[ERROR]" in res.stderr


def test_validate_l2_report_heading_order_and_placeholders():
    from scripts.validate_l2_report import _check_required_headings, _check_unreplaced_placeholders, _check_report_filename

    # 1. Valid report content
    valid_content = """# L2 Implementation Report
- **Role**: 15 data-engineer - OpenCode L2 Implementation
- **Gate**: TEST_GATE
- **Session**: l2_role15_test_20260823
- **Date**: 2026-08-23

## Summary
Valid summary.

## Repo-Local Files Read
- .agents/agent/data-engineer.md

## Changes Made
- scripts/dispatch_l2.py: updated

## Verification
- pytest passed

## Forbidden Path Scan
- .gemini\\antigravity-ide\\scratch\\ag-kit: absent; non-authoritative scan evidence only; no reliance.
"""
    ok, missing = _check_required_headings(valid_content)
    assert ok is True
    assert missing == []

    # 2. Missing top header
    no_header = valid_content.replace("# L2 Implementation Report\n", "")
    ok, missing = _check_required_headings(no_header)
    assert ok is False
    assert any("Missing top-level header" in m for m in missing)

    # 3. Out of order headings
    out_of_order_content = """# L2 Implementation Report
## Repo-Local Files Read
- .agents/agent/data-engineer.md

## Summary
Valid summary.

## Changes Made
- scripts/dispatch_l2.py: updated

## Verification
- pytest passed

## Forbidden Path Scan
- scan
"""
    ok, missing = _check_required_headings(out_of_order_content)
    assert ok is False
    assert any("out of order" in m for m in missing)

    # 4. Placeholders rejection: [SKILL_NAME] and [absent|not read]
    report_with_placeholders = """
- `.agents/skills/[SKILL_NAME]/SKILL.md`
- `.gemini\\antigravity-ide\\scratch\\ag-kit`: [absent|not read]; non-authoritative scan evidence only; no reliance.
- 1. Out of bounds: [passed/verified]
"""
    ok, found = _check_unreplaced_placeholders(report_with_placeholders)
    assert ok is False
    assert len(found) == 3
    assert any("[SKILL_NAME]" in f or "skill_name" in f for f in found)
    assert any("absent" in f for f in found)
    assert any("passed/verified" in f for f in found)

    # 5. Session ID path traversal rejection
    ok, msg = _check_report_filename("../evil_session_20260823")
    assert ok is False
    assert "traversal" in msg.lower()

    ok, msg = _check_report_filename("sub/dir/session_20260823")
    assert ok is False
    assert "traversal" in msg.lower()

    ok, msg = _check_report_filename("sub\\dir\\session_20260823")
    assert ok is False
    assert "traversal" in msg.lower()

    ok, msg = _check_report_filename("l2_role15_valid_task_20260823")
    assert ok is True
    assert msg == "OK"


def test_validate_l2_report_cli_path_traversal():
    res = subprocess.run(
        [
            sys.executable,
            "scripts/validate_l2_report.py",
            "../../etc/passwd",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert res.returncode == 2
    assert "ANTI_DRIP[E101]" in res.stdout or "ANTI_DRIP[E101]" in res.stderr


def test_lock_cleanup_safety_on_pair_bytes_failure(tmp_path):
    """Verify publish lock is released when _pair_bytes fails."""
    import hashlib
    import os
    import scripts.dispatch_l2 as dl2

    ev = tmp_path / "ev.json"
    ev.write_bytes(b'{"session":"1"}')
    pub_lock = ev.with_name(ev.name + ".publish.lock")
    assert not pub_lock.exists()

    with pytest.raises(RuntimeError, match="partial graph evidence artifact"):
        dl2._publish_graph_evidence(ev, b'{"session":"2"}', hashlib.sha256(b'{"session":"2"}').hexdigest())

    assert not pub_lock.exists(), "publish lock must be cleaned up when _pair_bytes fails"

    # Verify retry succeeds without lock contention
    ev.with_suffix(".sha256").write_text(hashlib.sha256(b'{"session":"1"}').hexdigest(), encoding="ascii")
    prev, pfd, plock = dl2._publish_graph_evidence(ev, b'{"session":"3"}', hashlib.sha256(b'{"session":"3"}').hexdigest())
    assert plock.exists()
    os.close(pfd)
    plock.unlink(missing_ok=True)
    assert not plock.exists()


def test_access_token_and_query_param_redaction():
    """Verify access_token, id_token, refresh_token query params in URLs are scrubbed."""
    from scripts.dispatch_l2 import redact_credentials, redact_sensitive_data

    url1 = "https://host/path?access_token=secret_token_123456789&x=1"
    assert redact_credentials(url1) == "https://host/path?access_token=[REDACTED]&x=1"
    assert "secret_token_123456789" not in redact_credentials(url1)

    # Percent-encoded parameter names in query string
    url_pct1 = "https://host/path?access%5Ftoken=secret_token_123456789&x=1"
    assert redact_credentials(url_pct1) == "https://host/path?access%5Ftoken=[REDACTED]&x=1"
    assert "secret_token_123456789" not in redact_credentials(url_pct1)

    url_pct2 = "https://host/path?access%2dtoken=secret_dash_999&api%2Dkey=my_key"
    assert redact_credentials(url_pct2) == "https://host/path?access%2dtoken=[REDACTED]&api%2Dkey=[REDACTED]"
    assert "secret_dash_999" not in redact_credentials(url_pct2)
    assert "my_key" not in redact_credentials(url_pct2)

    url2 = "https://example.com/api?id_token=my_id_token&refresh_token=my_refresh_token"
    assert redact_credentials(url2) == "https://example.com/api?id_token=[REDACTED]&refresh_token=[REDACTED]"
    assert "my_id_token" not in redact_credentials(url2)
    assert "my_refresh_token" not in redact_credentials(url2)

    url3 = "https://example.com/oauth?client_secret=secret_xyz&code=auth_code"
    assert redact_credentials(url3) == "https://example.com/oauth?client_secret=[REDACTED]&code=auth_code"
    assert "secret_xyz" not in redact_credentials(url3)

    assert redact_credentials("access_token=secret_token_123456789") == "access_token=[REDACTED]"
    assert redact_credentials("refresh_token=secret_refresh_999") == "refresh_token=[REDACTED]"
    assert redact_credentials("id_token=secret_id_111") == "id_token=[REDACTED]"
    assert "secret_id_111" not in redact_credentials("id_token=\"secret_id_111\"")
    assert "[REDACTED]" in redact_credentials("id_token=\"secret_id_111\"")
    assert redact_credentials("{\"access_token\": \"secret_token_123456789\"}") == "{\"access_token\": [REDACTED]}"
    assert redact_credentials("{\"refresh_token\": \"my_refresh\"}") == "{\"refresh_token\": [REDACTED]}"
    assert redact_credentials("{\"client_secret\": \"super_secret\"}") == "{\"client_secret\": [REDACTED]}"

    redacted = redact_sensitive_data({"api_key": "supersecret", "token": "abc123456", "private_key": "my_priv_key", "access_token": "acc_tok", "refresh_token": "ref_tok", "id_token": "id_tok", "client_secret": "c_sec", "access%5Ftoken": "pct_tok"})
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["token"] == "[REDACTED]"
    assert redacted["private_key"] == "[REDACTED]"
    assert redacted["access_token"] == "[REDACTED]"
    assert redacted["refresh_token"] == "[REDACTED]"
    assert redacted["id_token"] == "[REDACTED]"
    assert redacted["client_secret"] == "[REDACTED]"
    assert redacted["access%5Ftoken"] == "[REDACTED]"


def test_layered_encoding_deep_iterations_and_fail_closed_redaction():
    """Verify 20+, 30+, and 50+ stages of %25 percent-encoding for access_token and api-key."""
    from scripts.dispatch_l2 import redact_credentials, redact_sensitive_data

    def make_layered_key(base_key: str, depth: int) -> str:
        res = base_key
        for _ in range(depth):
            res = res.replace("%", "%25")
            res = res.replace("_", "%5F").replace("-", "%2D")
        return res

    for depth in (20, 30, 50, 60):
        # 1. access_token layered encoding
        enc_token_key = make_layered_key("access_token", depth)
        url_token = f"https://api.internal/v1?{enc_token_key}=TOPSECRET&unrelated=123"
        redacted_url_token = redact_credentials(url_token)
        assert "TOPSECRET" not in redacted_url_token
        assert "[REDACTED]" in redacted_url_token
        assert f"{enc_token_key}=[REDACTED]" in redacted_url_token

        dict_token = {enc_token_key: "TOPSECRET", "clean": "ok"}
        redacted_dict_token = redact_sensitive_data(dict_token)
        assert redacted_dict_token[enc_token_key] == "[REDACTED]"
        assert redacted_dict_token["clean"] == "ok"
        assert "TOPSECRET" not in str(redacted_dict_token)

        # 2. api-key layered encoding
        enc_api_key = make_layered_key("api-key", depth)
        url_api = f"https://api.internal/v1?{enc_api_key}=TOPSECRET&unrelated=456"
        redacted_url_api = redact_credentials(url_api)
        assert "TOPSECRET" not in redacted_url_api
        assert "[REDACTED]" in redacted_url_api
        assert f"{enc_api_key}=[REDACTED]" in redacted_url_api

        dict_api = {enc_api_key: "TOPSECRET", "clean": "ok"}
        redacted_dict_api = redact_sensitive_data(dict_api)
        assert redacted_dict_api[enc_api_key] == "[REDACTED]"
        assert redacted_dict_api["clean"] == "ok"
        assert "TOPSECRET" not in str(redacted_dict_api)

    # 3. Unresolvable (>100 depth) / infinite '%' fail-closed with sensitive stem
    infinite_pct_token = "%25" * 120 + "token"
    url_inf = f"https://api.internal/v1?{infinite_pct_token}=TOPSECRET"
    redacted_url_inf = redact_credentials(url_inf)
    assert "TOPSECRET" not in redacted_url_inf
    assert "[REDACTED]" in redacted_url_inf

    dict_inf = {infinite_pct_token: "TOPSECRET"}
    redacted_dict_inf = redact_sensitive_data(dict_inf)
    assert redacted_dict_inf[infinite_pct_token] == "[REDACTED]"

    # 4. Fully character-encoded secret keys with 101+, 120, 150 layers of %25
    # e.g. 'api_key' encoded char-by-char: %61%70%69%5F%6B%65%79
    # or 'access_token' encoded char-by-char: %61%63%63%65%73%73%5F%74%6F%6B%65%6E
    char_enc_api_key = "".join(f"%{ord(c):02x}" for c in "api_key")
    char_enc_access_token = "".join(f"%{ord(c):02x}" for c in "access_token")

    for layers in (101, 120, 150):
        # Layer char_enc_api_key with %25
        layered_key = char_enc_api_key
        for _ in range(layers):
            layered_key = layered_key.replace("%", "%25")

        url_char = f"https://api.internal/v1?{layered_key}=SUPER_SECRET_CHAR_ENC&unrelated=999"
        redacted_url_char = redact_credentials(url_char)
        assert "SUPER_SECRET_CHAR_ENC" not in redacted_url_char
        assert "[REDACTED]" in redacted_url_char
        assert f"{layered_key}=[REDACTED]" in redacted_url_char

        dict_char = {layered_key: "SUPER_SECRET_CHAR_ENC", "clean": "ok"}
        redacted_dict_char = redact_sensitive_data(dict_char)
        assert redacted_dict_char[layered_key] == "[REDACTED]"
        assert redacted_dict_char["clean"] == "ok"
        assert "SUPER_SECRET_CHAR_ENC" not in str(redacted_dict_char)

        # Layer char_enc_access_token with %25
        layered_token = char_enc_access_token
        for _ in range(layers):
            layered_token = layered_token.replace("%", "%25")

        url_tok = f"https://api.internal/v1?{layered_token}=SUPER_SECRET_TOKEN_ENC&unrelated=888"
        redacted_url_tok = redact_credentials(url_tok)
        assert "SUPER_SECRET_TOKEN_ENC" not in redacted_url_tok
        assert "[REDACTED]" in redacted_url_tok
        assert f"{layered_token}=[REDACTED]" in redacted_url_tok

        dict_tok = {layered_token: "SUPER_SECRET_TOKEN_ENC"}
        redacted_dict_tok = redact_sensitive_data(dict_tok)
        assert redacted_dict_tok[layered_token] == "[REDACTED]"
        assert "SUPER_SECRET_TOKEN_ENC" not in str(redacted_dict_tok)


def test_f1_base_exception_rollback_and_lock_unlink(tmp_path):
    """F1 & F2: Catch BaseException (KeyboardInterrupt) and nested finally unlink."""
    import hashlib
    import os
    import scripts.dispatch_l2 as dl2

    ev = tmp_path / "ev.json"
    ev.write_bytes(b'{"session":"1"}')
    ev.with_suffix(".sha256").write_text(hashlib.sha256(b'{"session":"1"}').hexdigest(), encoding="ascii")
    pub_lock = ev.with_name(ev.name + ".publish.lock")

    orig_replace = os.replace
    def raise_interrupt(src, dst):
        if str(src).endswith(".tmp"):
            raise KeyboardInterrupt("Simulated Ctrl+C")
        return orig_replace(src, dst)

    try:
        os.replace = raise_interrupt
        with pytest.raises(RuntimeError, match="graph evidence publication and rollback failed"):
            dl2._publish_graph_evidence(ev, b'{"session":"2"}', hashlib.sha256(b'{"session":"2"}').hexdigest())
    finally:
        os.replace = orig_replace

    assert not pub_lock.exists(), "publish lock must be unlinked even on KeyboardInterrupt"
    assert ev.read_bytes() == b'{"session":"1"}', "evidence must be preserved on KeyboardInterrupt rollback"


def test_f2_lock_cleanup_nested_finally_on_close_oserror(tmp_path):
    """F2: Lock file is unlinked even if os.close(fd) raises OSError."""
    import hashlib
    import os
    import scripts.dispatch_l2 as dl2

    ev = tmp_path / "ev.json"
    ev.write_bytes(b'{"session":"1"}')
    ev.with_suffix(".sha256").write_text(hashlib.sha256(b'{"session":"1"}').hexdigest(), encoding="ascii")
    pub_lock = ev.with_name(ev.name + ".publish.lock")

    orig_close = os.close
    orig_replace = os.replace
    def flaky_close(fd):
        orig_close(fd)
        raise OSError("Simulated close OSError")

    def fail_replace(*args, **kwargs):
        raise RuntimeError("Replace failed")

    try:
        os.replace = fail_replace
        os.close = flaky_close
        with pytest.raises(RuntimeError):
            dl2._publish_graph_evidence(ev, b'{"session":"2"}', hashlib.sha256(b'{"session":"2"}').hexdigest())
    finally:
        os.close = orig_close
        os.replace = orig_replace

    assert not pub_lock.exists(), "publish lock must be unlinked even when os.close raises OSError"


def test_f1_run_graph_predispatch_gate_post_publication_base_exception_rollback(tmp_path, monkeypatch):
    """F1: In run_graph_predispatch_gate around post-publication verification, catch BaseException (KeyboardInterrupt)
    and restore/verify previous evidence pair before releasing descriptor and lock in finally."""
    import hashlib
    import scripts.dispatch_l2 as dl2

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir(parents=True)
    session_dir = repo_dir / ".ly_state" / "session"
    session_dir.mkdir(parents=True)

    session_id = "test_f1_rollback"
    ev_path = session_dir / f"graph_evidence_{session_id}.json"
    sha_path = ev_path.with_suffix(".sha256")
    pub_lock = ev_path.with_name(ev_path.name + ".publish.lock")

    # Initial evidence pair
    initial_bytes = b'{"initial":"state"}'
    initial_sha = hashlib.sha256(initial_bytes).hexdigest()
    ev_path.write_bytes(initial_bytes)
    sha_path.write_text(initial_sha, encoding="ascii")

    # Mock dependencies of run_graph_predispatch_gate
    monkeypatch.setattr(dl2, "GRAPH_TOOL_ROOT", tmp_path)
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    monkeypatch.setattr(dl2, "_scope_files", lambda scope, root: ["a.py"])
    monkeypatch.setattr(dl2, "_scope_content_hashes", lambda root, files: {"a.py": "hash1"})
    monkeypatch.setattr(dl2, "_is_scope_dirty", lambda root, files: False)
    monkeypatch.setattr(dl2, "_current_commit", lambda root: "abcdef1234567890")
    monkeypatch.setattr(dl2, "_graph_commit", lambda: "abcdef1234567890")

    class FakeProc:
        stdout = "status: abcdef123456 ok"
    monkeypatch.setattr(dl2, "_run_checked", lambda cmd, cwd, timeout: FakeProc())
    monkeypatch.setattr(dl2, "_bounded_impact_query", lambda root, files: ({"summary": "s", "impacted_files": [], "total_impacted": 0, "truncated": False}, {"complete": True, "batch_count": 1}))
    monkeypatch.setattr(dl2, "_graph_file_summary", lambda root, p: ({"summary": "ok"}, False))

    # Simulate KeyboardInterrupt during post-publication verification
    orig_scope_hashes = dl2._scope_content_hashes
    call_count = 0
    def post_pub_scope_hashes(root, files):
        nonlocal call_count
        call_count += 1
        # 1st call is initial_scope_hashes, 2nd is final_scope_hashes, 3rd is post_pub_hashes
        if call_count >= 3:
            raise KeyboardInterrupt("Simulated Ctrl+C during post-pub verification")
        return {"a.py": "hash1"}

    monkeypatch.setattr(dl2, "_scope_content_hashes", post_pub_scope_hashes)

    with pytest.raises(KeyboardInterrupt) as excinfo:
        dl2.run_graph_predispatch_gate(session_id, "a.py", repo_dir)
    assert "Simulated Ctrl+C" in str(excinfo.value)

    assert not pub_lock.exists(), "publish lock must be unlinked after post-pub BaseException"
    assert ev_path.read_bytes() == initial_bytes, "previous evidence must be restored"
    assert sha_path.read_text(encoding="ascii").strip() == initial_sha, "previous sha must be restored"


def test_f3_sentinel_lock_preservation():
    """F3/F1: Sentinel / concurrent locks survive fixture setup and teardown without being touched."""
    session_dir = REPO_ROOT / ".ly_state" / "session"
    session_dir.mkdir(parents=True, exist_ok=True)
    sentinel_lock = session_dir / "dispatch_sentinel_lock_do_not_delete.lock"
    sentinel_lock.write_text("99999", encoding="ascii")

    try:
        # Run test fixture logic or session lock functions
        import scripts.dispatch_l2 as dl2
        test_lock = session_dir / "dispatch_test_temp_unique_123.lock"
        test_lock.write_text("12345", encoding="ascii")
        dl2.release_session_lock(test_lock)
        assert not test_lock.exists()
        assert sentinel_lock.exists(), "sentinel lock must never be touched or unlinked"
    finally:
        sentinel_lock.unlink(missing_ok=True)


def test_sentinel_lock_survives_fixture_setup_and_teardown():
    """Verify that external sentinel locks (created before or during test) survive fixture setup and teardown."""
    session_dir = REPO_ROOT / ".ly_state" / "session"
    session_dir.mkdir(parents=True, exist_ok=True)
    external_sentinel = session_dir / "dispatch_external_sentinel_survive.lock"
    external_sentinel.write_text("external_pid_8888", encoding="ascii")

    try:
        # Generator iteration simulating inner fixture run
        gen = _session_locks_cleanup_context()
        tracked_set = next(gen)
        # Verify external sentinel is not in tracked set
        assert external_sentinel not in tracked_set
        # Create a test-tracked lock
        test_tracked_lock = session_dir / "dispatch_test_tracked_lock.lock"
        test_tracked_lock.write_text("11111", encoding="ascii")
        tracked_set.add(test_tracked_lock)

        # Run teardown
        try:
            next(gen)
        except StopIteration:
            pass

        # Verify test-tracked lock was cleaned up
        assert not test_tracked_lock.exists()
        # Verify external sentinel lock survived untouched
        assert external_sentinel.exists()
        assert external_sentinel.read_text(encoding="ascii") == "external_pid_8888"
    finally:
        external_sentinel.unlink(missing_ok=True)


def test_f4_double_encoded_query_param_redaction():
    """F4: Double-encoded query keys (e.g. access%255Ftoken, api%252Dkey, etc.) are unquoted up to 5 passes and redacted."""
    from scripts.dispatch_l2 import redact_credentials

    # Double percent-encoded: %255F -> %5F -> _
    url_double_1 = "https://host/path?access%255Ftoken=supersecret123&other=param"
    redacted_1 = redact_credentials(url_double_1)
    assert redacted_1 == "https://host/path?access%255Ftoken=[REDACTED]&other=param"
    assert "supersecret123" not in redacted_1

    # Double percent-encoded: %252D -> %2D -> -
    url_double_2 = "https://host/path?api%252Dkey=secretapikey999&x=1"
    redacted_2 = redact_credentials(url_double_2)
    assert redacted_2 == "https://host/path?api%252Dkey=[REDACTED]&x=1"
    assert "secretapikey999" not in redacted_2

    # Triple percent-encoded: %25255F -> %255F -> %5F -> _
    url_triple = "https://host/path?access%25255Ftoken=triple_secret&x=1"
    redacted_3 = redact_credentials(url_triple)
    assert redacted_3 == "https://host/path?access%25255Ftoken=[REDACTED]&x=1"
    assert "triple_secret" not in redacted_3

    # Preserves raw non-secret key
    url_safe = "https://host/path?user%252Dname=john&page=1"
    assert redact_credentials(url_safe) == "https://host/path?user%252Dname=john&page=1"


def test_f2_deeply_nested_encoding_redaction_and_key_normalization():
    """F2: Deeply nested percent-encodings (up to 20 passes) are 100% redacted in URLs and dict keys while preserving raw syntax."""
    from scripts.dispatch_l2 import redact_credentials, redact_sensitive_data, _normalize_secret_key

    assert _normalize_secret_key("access%25252525255Ftoken") == "access_token"
    assert _normalize_secret_key("api%252Dkey") == "api_key"

    # Deeply nested URL query param
    nested_url = "https://example.com/api?access%25252525255Ftoken=URL_TOPSECRET&safe%2525252Dparam=safe_val"
    redacted_url = redact_credentials(nested_url)
    assert redacted_url == "https://example.com/api?access%25252525255Ftoken=[REDACTED]&safe%2525252Dparam=safe_val"
    assert "URL_TOPSECRET" not in redacted_url
    assert "access%25252525255Ftoken" in redacted_url

    # Deeply nested dictionary key
    nested_dict = {
        "api%252Dkey": "DICT_TOPSECRET",
        "nested": {
            "client%252525255Fsecret": "NESTED_TOPSECRET",
            "normal_key": "normal_val"
        }
    }
    redacted_dict = redact_sensitive_data(nested_dict)
    assert redacted_dict["api%252Dkey"] == "[REDACTED]"
    assert redacted_dict["nested"]["client%252525255Fsecret"] == "[REDACTED]"
    assert redacted_dict["nested"]["normal_key"] == "normal_val"
    assert "DICT_TOPSECRET" not in str(redacted_dict)
    assert "NESTED_TOPSECRET" not in str(redacted_dict)


def test_separator_variants_and_encoded_separators_redaction():
    """F1: Whitespace, +, ., %20, %09, %2B, %2E separators in URL queries, dict keys, generic text, and lesson fields."""
    from scripts.dispatch_l2 import (
        redact_credentials,
        redact_sensitive_data,
        sanitize_lesson_field,
        _normalize_secret_key,
    )

    # 1. _normalize_secret_key tests
    assert _normalize_secret_key("api key") == "api_key"
    assert _normalize_secret_key("api.key") == "api_key"
    assert _normalize_secret_key("api+key") == "api_key"
    assert _normalize_secret_key("api%20key") == "api_key"
    assert _normalize_secret_key("api%09key") == "api_key"
    assert _normalize_secret_key("api%2Bkey") == "api_key"
    assert _normalize_secret_key("api%2Ekey") == "api_key"
    assert _normalize_secret_key("private.key") == "private_key"
    assert _normalize_secret_key("private key") == "private_key"
    assert _normalize_secret_key("private+key") == "private_key"
    assert _normalize_secret_key("client.secret") == "client_secret"
    assert _normalize_secret_key("client secret") == "client_secret"
    assert _normalize_secret_key("client+secret") == "client_secret"
    assert _normalize_secret_key("access.token") == "access_token"
    assert _normalize_secret_key("refresh.token") == "refresh_token"

    # 2. URL queries with various separators
    urls = [
        "https://host/api?api%20key=CANARY_VAL1&x=1",
        "https://host/api?api+key=CANARY_VAL2&x=1",
        "https://host/api?api.key=CANARY_VAL3&x=1",
        "https://host/api?api%09key=CANARY_VAL4&x=1",
        "https://host/api?api%2Bkey=CANARY_VAL5&x=1",
        "https://host/api?api%2Ekey=CANARY_VAL6&x=1",
        "https://host/api?client.secret=CANARY_VAL7&x=1",
        "https://host/api?client+secret=CANARY_VAL8&x=1",
        "https://host/api?client%20secret=CANARY_VAL9&x=1",
        "https://host/api?private.key=CANARY_VAL10&x=1",
        "https://host/api?private+key=CANARY_VAL11&x=1",
        "https://host/api?private%20key=CANARY_VAL12&x=1",
        "https://host/api?access.token=CANARY_VAL13&x=1",
        "https://host/api?access+token=CANARY_VAL14&x=1",
        "https://host/api?access%20token=CANARY_VAL15&x=1",
    ]
    for url in urls:
        redacted = redact_credentials(url)
        assert "CANARY_VAL" not in redacted
        assert "[REDACTED]" in redacted

    # 3. Dictionary keys with separator variants
    d = {
        "api key": "CANARY_DICT1",
        "api.key": "CANARY_DICT2",
        "api+key": "CANARY_DICT3",
        "api%20key": "CANARY_DICT4",
        "api%09key": "CANARY_DICT5",
        "api%2Bkey": "CANARY_DICT6",
        "api%2Ekey": "CANARY_DICT7",
        "private.key": "CANARY_DICT8",
        "private key": "CANARY_DICT9",
        "private+key": "CANARY_DICT10",
        "client.secret": "CANARY_DICT11",
        "client secret": "CANARY_DICT12",
        "client+secret": "CANARY_DICT13",
        "access.token": "CANARY_DICT14",
        "refresh.token": "CANARY_DICT15",
        "safe_key": "safe_val",
    }
    redacted_d = redact_sensitive_data(d)
    for k in d:
        if k == "safe_key":
            assert redacted_d[k] == "safe_val"
        else:
            assert redacted_d[k] == "[REDACTED]"
    assert "CANARY_DICT" not in str(redacted_d)

    # 4. Generic text / key-value string redaction
    texts = [
        "api key: CANARY_TXT1",
        "api.key: CANARY_TXT2",
        "api+key: CANARY_TXT3",
        "api\tkey: CANARY_TXT4",
        "client.secret: CANARY_TXT5",
        "client secret: CANARY_TXT6",
        "client+secret: CANARY_TXT7",
        "private.key: CANARY_TXT8",
        "private key: CANARY_TXT9",
        "private+key: CANARY_TXT10",
        "access.token: CANARY_TXT11",
        "access token: CANARY_TXT12",
        "refresh.token: CANARY_TXT13",
        "api key = CANARY_TXT14",
        "api.key = CANARY_TXT15",
    ]
    for text in texts:
        redacted = redact_credentials(text)
        assert "CANARY_TXT" not in redacted
        assert "[REDACTED]" in redacted

    # 5. Lesson fields sanitization
    lesson_fields = [
        "Found error when api key: CANARY_LESSON1 occurred in gateway",
        "Check private.key: CANARY_LESSON2 in config",
        "OAuth failed client.secret: CANARY_LESSON3 invalid",
        "Request failed with https://api.com?api.key=CANARY_LESSON4&user=1",
        "Auth token expired at https://auth.com?access%20token=CANARY_LESSON5",
    ]
    for field in lesson_fields:
        sanitized = sanitize_lesson_field(field)
        assert "CANARY_LESSON" not in sanitized
        assert "[REDACTED]" in sanitized

    # 6. Exact reproduction test for percent-encoded separators in generic text and lesson fields
    for key in ('api%20key', 'api%09key', 'api%2Bkey', 'api%2Ekey', 'private%2Ekey', 'client%20secret'):
        test_payload = f'{key}: CANARY_SECRET'
        redacted = redact_credentials(test_payload)
        sanitized = sanitize_lesson_field(test_payload)
        assert 'CANARY_SECRET' not in redacted
        assert '[REDACTED]' in redacted
        assert 'CANARY_SECRET' not in sanitized
        assert '[REDACTED]' in sanitized

    # 7. Exact reproduction test for layered percent-encoded separators (%2520, %252E, %252B, %2509)
    layered_keys = (
        'api%2520key',
        'client%2520secret',
        'private%252Ekey',
        'api%252Bkey',
        'api%2509key',
        'api%252520key',
        'client%252520secret',
        'private%25252Ekey',
        'api%25252Bkey',
        'api%252509key',
    )
    for key in layered_keys:
        for template in (f'{key}: CANARY_SECRET', f'{key}=CANARY_SECRET'):
            redacted = redact_credentials(template)
            sanitized = sanitize_lesson_field(template)
            assert 'CANARY_SECRET' not in redacted
            assert '[REDACTED]' in redacted
            assert 'CANARY_SECRET' not in sanitized
            assert '[REDACTED]' in sanitized

    # 8. Colon-bearing equals values redaction (Finding F1)
    colon_bearing_templates = (
        ('api_key=SECRET:TAIL', 'api_key=[REDACTED]'),
        ('api%2520key=SECRET:TAIL', 'api%2520key=[REDACTED]'),
        ('client_secret=SECRET:WITH:COLONS', 'client_secret=[REDACTED]'),
    )
    for raw_input, expected in colon_bearing_templates:
        redacted = redact_credentials(raw_input)
        sanitized = sanitize_lesson_field(raw_input)
        assert 'SECRET' not in redacted
        assert redacted == expected
        assert 'SECRET' not in sanitized
        assert sanitized == expected


def test_escaped_quote_redaction_and_linear_speed_bounds():
    """F1 & F2: Verify escaped quotes inside quoted values are 100% redacted and sanitize_lesson_field/redact_credentials handle 100k length input linearly under 0.1s."""
    import time
    from scripts.dispatch_l2 import redact_credentials, sanitize_lesson_field

    # 1. Escaped quotes in JSON and single-quoted strings
    escaped_cases = [
        (r'{"api_key":"HEAD\"CANARY_TAIL"}', '{"api_key": [REDACTED]}'),
        (r'api_key="HEAD\"CANARY_TAIL"', 'api_key=[REDACTED]'),
        (r"api_key='HEAD\'CANARY_TAIL'", "api_key=[REDACTED]"),
        (r'{"client_secret":"VALUE_WITH_ESCAPED_\"_QUOTE_CANARY"}', '{"client_secret": [REDACTED]}'),
        (r'private_key: "ESCAPED\\\"DOUBLE\\\"QUOTE_CANARY"', 'private_key: [REDACTED]'),
        (r'{"access_token":"MULTI\"ESCAPED\"CANARY\"TEST"}', '{"access_token": [REDACTED]}'),
    ]
    for raw_val, expected in escaped_cases:
        redacted = redact_credentials(raw_val)
        sanitized = sanitize_lesson_field(raw_val)
        assert "CANARY" not in redacted
        assert "HEAD" not in redacted
        assert "[REDACTED]" in redacted
        assert "CANARY" not in sanitized
        assert "HEAD" not in sanitized
        assert "[REDACTED]" in sanitized

    # 2. Linear speed test on 100,000 char long input
    long_safe_string = "x" * 100000
    t0 = time.perf_counter()
    sanitized_long = sanitize_lesson_field(long_safe_string)
    t_sanitize = time.perf_counter() - t0
    assert len(sanitized_long) <= 200
    assert t_sanitize < 0.5, f"sanitize_lesson_field took {t_sanitize}s on 100k string"

    t1 = time.perf_counter()
    redacted_long = redact_credentials(long_safe_string)
    t_redact = time.perf_counter() - t1
    assert t_redact < 0.5, f"redact_credentials took {t_redact}s on 100k string"

    # 3. 100k char string with secret embedded at various positions
    long_with_secret_head = r'{"api_key":"HEAD\"CANARY_TAIL"}' + ("y" * 100000)
    t2 = time.perf_counter()
    redacted_head = redact_credentials(long_with_secret_head)
    t_head = time.perf_counter() - t2
    assert "CANARY" not in redacted_head
    assert "[REDACTED]" in redacted_head
    assert t_head < 0.5

    sanitized_head = sanitize_lesson_field(long_with_secret_head)
    assert "CANARY" not in sanitized_head
    assert "[REDACTED]" in sanitized_head


def test_long_credential_redaction_and_unterminated_quotes():
    """F1 from role21: Assert CANARY_SECRET is absent from sanitize_lesson_field with 100 repetitions of CANARY_SECRET and unterminated quotes."""
    from scripts.dispatch_l2 import redact_credentials, sanitize_lesson_field

    # 1. Long quoted credentials exceeding previous 800-char pre-truncation cap
    long_secret = "CANARY_SECRET_" * 100
    test_cases = [
        f'api_key="{long_secret}"',
        f"api_key='{long_secret}'",
        f'api_key="{long_secret}',  # unterminated double quote at EOF
        f"api_key='{long_secret}",  # unterminated single quote at EOF
        f'{{"api_key": "{long_secret}"}}',
        f'secret: "{long_secret}"',
        f'secret: "{long_secret}',  # unterminated
        f'secret=\'{long_secret}',  # unterminated
        f'{{"client_secret":"{long_secret}"}}',
    ]

    for raw in test_cases:
        redacted = redact_credentials(raw)
        sanitized = sanitize_lesson_field(raw)
        assert "CANARY_SECRET" not in redacted, f"CANARY_SECRET leaked in redact_credentials for: {raw[:40]}"
        assert "[REDACTED]" in redacted
        assert "CANARY_SECRET" not in sanitized, f"CANARY_SECRET leaked in sanitize_lesson_field for: {raw[:40]}"
        assert "[REDACTED]" in sanitized
        assert len(sanitized) <= 200

    # 2. Unterminated quotes with escaped characters
    escaped_unterminated = r'api_key="ESCAPED\"CANARY_SECRET_TAIL'
    redacted_esc = redact_credentials(escaped_unterminated)
    sanitized_esc = sanitize_lesson_field(escaped_unterminated)
    assert "CANARY_SECRET" not in redacted_esc
    assert "CANARY_SECRET" not in sanitized_esc
    assert "[REDACTED]" in redacted_esc
    assert "[REDACTED]" in sanitized_esc


ANTI_GATE = "TEST_ANTI_DRIP_GATE_20260907"
ANTI_SESSION = "l2_role11_anti_drip_test_20260907"


def _audit(gate: str, verdict: str, timestamp: str, *, finding: bool = False) -> str:
    suffix = ""
    if finding:
        suffix = """
## 16-Dimension Adversarial Matrix

| Dimension | Name | Result |
|---:|---|---|
| 16 | Secret redaction | [FAIL] |

## Blocking Findings

### F-004 - Plaintext backup survives replacement failure

- **Severity**: High
- **Probe output**: `BACKUP_LEAK=True`
"""
    return f"""# Audit

- **Gate**: `{gate}`
- **Audit Timestamp**: `{timestamp}`

## Verdict

- **Final Verdict**: **[{verdict}]**
{suffix}
"""


def test_latest_approved_audit_overrides_older_needs_fix(tmp_path):
    audit_dir = tmp_path / ".ly_state/session/audit_reports"
    audit_dir.mkdir(parents=True)
    old = audit_dir / "role21_test_anti_drip_gate_20260907_cycle11.md"
    final = audit_dir / "role21_test_anti_drip_gate_20260907.md"
    old.write_text(_audit(ANTI_GATE, "NEEDS_FIX", "2026-09-06T20:00:00+00:00", finding=True), encoding="utf-8")
    final.write_text(_audit(ANTI_GATE, "APPROVED", "2026-09-06T21:00:00+00:00"), encoding="utf-8")
    outcome = dispatch_l2.extract_prior_audit_outcomes(ANTI_GATE, tmp_path)
    assert outcome is not None
    assert outcome.report_path == final
    assert outcome.verdict == "APPROVED"
    assert dispatch_l2.build_anti_drip_contract(ANTI_SESSION, ANTI_GATE, tmp_path, outcome)["mode"] == "baseline"


def test_remediation_extracts_structured_finding_and_sanitizes_secret(tmp_path):
    audit_dir = tmp_path / ".ly_state/session/audit_reports"
    audit_dir.mkdir(parents=True)
    report = audit_dir / "role21_test_anti_drip_gate_20260907_cycle11.md"
    content = _audit(ANTI_GATE, "NEEDS_FIX", "2026-09-06T20:00:00+00:00", finding=True)
    content += "- **Probe output**: `api_key=LEAK`\n"
    report.write_text(content, encoding="utf-8")
    assert dispatch_l2._parse_dimensions(content, report)[1]
    assert dispatch_l2._extract_audit_findings(content, report)
    outcome = dispatch_l2.extract_prior_audit_outcomes(ANTI_GATE, tmp_path)
    assert outcome is not None
    assert outcome.findings == (dispatch_l2.AuditFinding(
        "F-004", "high", "Plaintext backup survives replacement failure", ("BACKUP_LEAK=True",)
    ),)


def test_conflicting_latest_verdict_fails_closed(tmp_path):
    audit_dir = tmp_path / ".ly_state/session/audit_reports"
    audit_dir.mkdir(parents=True)
    report = audit_dir / "role21_test_anti_drip_gate_20260907.md"
    report.write_text(_audit(ANTI_GATE, "APPROVED", "2026-09-06T21:00:00+00:00") + "\n- **Status**: [NEEDS_FIX]\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="missing or conflicting"):
        dispatch_l2.extract_prior_audit_outcomes(ANTI_GATE, tmp_path)


def test_contract_atomic_pair_and_prompt_binding(tmp_path):
    contract = dispatch_l2.build_anti_drip_contract(ANTI_SESSION, ANTI_GATE, tmp_path, None)
    path, sidecar, digest = dispatch_l2.write_anti_drip_contract(tmp_path, ANTI_SESSION, contract)
    assert path.read_bytes() == dispatch_l2.canonical_json_bytes(contract)
    assert sidecar.read_bytes() == f"{digest}  {path.name}\n".encode("ascii")
    clause = dispatch_l2.build_anti_drip_prompt_clause(path, digest, contract, tmp_path)
    assert clause.splitlines().count(dispatch_l2.PROMPT_BEGIN_MARKER) == 1
    assert [line.split(")", 1)[0][1:] for line in clause.splitlines() if line.startswith("(AD-")] == [f"AD-{n}" for n in range(1, 7)]


def test_contract_atomic_failure_leaves_no_temp_files(tmp_path, monkeypatch):
    contract = dispatch_l2.build_anti_drip_contract(ANTI_SESSION, ANTI_GATE, tmp_path, None)
    real_replace = os.replace
    calls = 0
    def fail_second(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected sidecar failure")
        real_replace(source, destination)
    monkeypatch.setattr(dispatch_l2.os, "replace", fail_second)
    with pytest.raises(RuntimeError, match="atomic publication"):
        dispatch_l2.write_anti_drip_contract(tmp_path, ANTI_SESSION, contract)
    assert not list((tmp_path / ".ly_state/session").glob("tmp*"))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), [object()]])
def test_canonical_json_rejects_non_json_or_nonfinite(value):
    with pytest.raises((ValueError, TypeError)):
        dispatch_l2.canonical_json_bytes({"value": value})


def _make_valid_impact_payload(scope_files: list[str], total: int = 10, impacted: list[str] | None = None) -> dict:
    return {
        "status": "ok",
        "summary": "Impact summary",
        "changed_files": list(scope_files),
        "impacted_files": list(scope_files if impacted is None else impacted),
        "total_impacted": total,
        "truncated": False,
        "nodes_omitted": 0,
    }


def test_bounded_impact_query_laddering_on_truncation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    file_a = tmp_path / "a.py"
    file_a.write_text("print(1)", encoding="utf-8")
    attempts = []

    def fake_graph_json(repo_root, *args):
        max_res = args[args.index("--max-results") + 1]
        attempts.append(max_res)
        if max_res == "100":
            raise RuntimeError("graph impact response is truncated; complete representation is required")
        if max_res == "150":
            return _make_valid_impact_payload(["a.py"], total=120)
        raise RuntimeError("unexpected max_results")

    monkeypatch.setattr(dispatch_l2, "_graph_json", fake_graph_json)
    merged, protocol = dispatch_l2._bounded_impact_query(tmp_path, ["a.py"])

    assert attempts == ["100", "150"]
    assert protocol["batch_count"] == 1
    assert protocol["complete"] is True
    assert merged["total_impacted"] == 120
    assert merged["impacted_files"] == ["a.py"]
    assert merged["truncated"] is False


def test_bounded_impact_query_laddering_on_omitted_nodes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    file_a = tmp_path / "a.py"
    file_a.write_text("print(1)", encoding="utf-8")
    attempts = []

    def fake_graph_json(repo_root, *args):
        max_res = args[args.index("--max-results") + 1]
        attempts.append(max_res)
        if max_res == "100":
            raise RuntimeError("graph impact response omitted nodes; complete representation is required")
        if max_res == "150":
            return _make_valid_impact_payload(["a.py"], total=115)
        raise RuntimeError("unexpected max_results")

    monkeypatch.setattr(dispatch_l2, "_graph_json", fake_graph_json)
    merged, protocol = dispatch_l2._bounded_impact_query(tmp_path, ["a.py"])

    assert attempts == ["100", "150"]
    assert protocol["batch_count"] == 1
    assert merged["total_impacted"] == 115
    assert merged["truncated"] is False


def test_bounded_impact_query_full_ladder_to_250(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    file_a = tmp_path / "a.py"
    file_a.write_text("print(1)", encoding="utf-8")
    attempts = []

    def fake_graph_json(repo_root, *args):
        max_res = args[args.index("--max-results") + 1]
        attempts.append(max_res)
        if max_res in ("100", "150"):
            raise RuntimeError("graph impact response is truncated; complete representation is required")
        if max_res == "200":
            raise RuntimeError("graph impact response omitted nodes; complete representation is required")
        if max_res == "250":
            return _make_valid_impact_payload(["a.py"], total=240)
        raise RuntimeError("unexpected max_results")

    monkeypatch.setattr(dispatch_l2, "_graph_json", fake_graph_json)
    merged, protocol = dispatch_l2._bounded_impact_query(tmp_path, ["a.py"])

    assert attempts == ["100", "150", "200", "250"]
    assert protocol["batch_count"] == 1
    assert merged["total_impacted"] == 240


def test_bounded_impact_query_bisection_after_ladder_exhaustion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    file_a = tmp_path / "a.py"
    file_b = tmp_path / "b.py"
    file_a.write_text("print(1)", encoding="utf-8")
    file_b.write_text("print(2)", encoding="utf-8")
    query_log = []

    def fake_graph_json(repo_root, *args):
        files = []
        i = args.index("--files") + 1
        while i < len(args) and not args[i].startswith("--"):
            files.append(args[i])
            i += 1
        max_res = args[args.index("--max-results") + 1]
        query_log.append((tuple(files), max_res))

        if files == ["a.py", "b.py"]:
            # Exhaust all ladder steps for combined batch
            raise RuntimeError("graph impact response is truncated; complete representation is required")
        if files == ["a.py"]:
            # a.py succeeds at 100
            return _make_valid_impact_payload(["a.py"], total=30)
        if files == ["b.py"]:
            # b.py truncates at 100, succeeds at 150
            if max_res == "100":
                raise RuntimeError("graph impact response omitted nodes; complete representation is required")
            return _make_valid_impact_payload(["b.py"], total=135)
        raise RuntimeError(f"unexpected files: {files}")

    monkeypatch.setattr(dispatch_l2, "_graph_json", fake_graph_json)
    merged, protocol = dispatch_l2._bounded_impact_query(tmp_path, ["a.py", "b.py"])

    # First combined was tried for 100, 150, 200, 250
    assert (("a.py", "b.py"), "100") in query_log
    assert (("a.py", "b.py"), "150") in query_log
    assert (("a.py", "b.py"), "200") in query_log
    assert (("a.py", "b.py"), "250") in query_log

    # Then bisected: a.py tried at 100, b.py tried at 100 then 150
    assert (("a.py",), "100") in query_log
    assert (("b.py",), "100") in query_log
    assert (("b.py",), "150") in query_log

    assert protocol["batch_count"] == 2
    assert protocol["complete"] is True
    assert protocol["covered_scope_count"] == 2
    assert merged["total_impacted"] == 165
    assert merged["impacted_files"] == ["a.py", "b.py"]
    assert merged["truncated"] is False


def test_bounded_impact_query_single_file_ladder_exhaustion_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    file_a = tmp_path / "a.py"
    file_a.write_text("print(1)", encoding="utf-8")
    attempts = []

    def fake_graph_json(repo_root, *args):
        max_res = args[args.index("--max-results") + 1]
        attempts.append(max_res)
        raise RuntimeError("graph impact response is truncated; complete representation is required")

    monkeypatch.setattr(dispatch_l2, "_graph_json", fake_graph_json)

    with pytest.raises(RuntimeError) as excinfo:
        dispatch_l2._bounded_impact_query(tmp_path, ["a.py"])

    assert attempts == ["100", "150", "200", "250"]
    assert "safe complete representation is impossible" in str(excinfo.value)
    assert "max_results=250" in str(excinfo.value)


def test_bounded_impact_query_byte_limit_bisects_without_laddering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    file_a = tmp_path / "a.py"
    file_b = tmp_path / "b.py"
    file_a.write_text("print(1)", encoding="utf-8")
    file_b.write_text("print(2)", encoding="utf-8")
    query_log = []

    def fake_graph_json(repo_root, *args):
        files = []
        i = args.index("--files") + 1
        while i < len(args) and not args[i].startswith("--"):
            files.append(args[i])
            i += 1
        max_res = args[args.index("--max-results") + 1]
        query_log.append((tuple(files), max_res))

        if files == ["a.py", "b.py"]:
            raise RuntimeError("command output exceeded safe byte limit")
        return _make_valid_impact_payload(files, total=10)

    monkeypatch.setattr(dispatch_l2, "_graph_json", fake_graph_json)
    merged, protocol = dispatch_l2._bounded_impact_query(tmp_path, ["a.py", "b.py"])

    # Byte limit should break immediately on 100 without trying 150, 200, 250
    assert query_log == [
        (("a.py", "b.py"), "100"),
        (("a.py",), "100"),
        (("b.py",), "100"),
    ]
    assert protocol["batch_count"] == 2
    assert protocol["complete"] is True
    assert merged["total_impacted"] == 20


def test_bounded_impact_query_byte_limit_single_file_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    file_a = tmp_path / "a.py"
    file_a.write_text("print(1)", encoding="utf-8")
    attempts = []

    def fake_graph_json(repo_root, *args):
        max_res = args[args.index("--max-results") + 1]
        attempts.append(max_res)
        raise RuntimeError("graph query JSON exceeded safe byte limit")

    monkeypatch.setattr(dispatch_l2, "_graph_json", fake_graph_json)

    with pytest.raises(RuntimeError) as excinfo:
        dispatch_l2._bounded_impact_query(tmp_path, ["a.py"])

    # For byte limit, does not ladder to 150, 200, 250 since output is already too large
    assert attempts == ["100"]
    assert "safe complete representation is impossible" in str(excinfo.value)


def test_bounded_impact_query_unhandled_error_fails_closed_immediately(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    file_a = tmp_path / "a.py"
    file_b = tmp_path / "b.py"
    file_a.write_text("print(1)", encoding="utf-8")
    file_b.write_text("print(2)", encoding="utf-8")
    attempts = []

    def fake_graph_json(repo_root, *args):
        attempts.append(args[args.index("--max-results") + 1])
        raise RuntimeError("graph query returned malformed JSON")

    monkeypatch.setattr(dispatch_l2, "_graph_json", fake_graph_json)

    with pytest.raises(RuntimeError, match="graph query returned malformed JSON"):
        dispatch_l2._bounded_impact_query(tmp_path, ["a.py", "b.py"])

    # Immediate fail-closed, no laddering or bisection on unexpected error
    assert attempts == ["100"]


def test_bounded_impact_query_empty_scope(tmp_path: Path):
    merged, protocol = dispatch_l2._bounded_impact_query(tmp_path, [])
    assert protocol["batch_count"] == 0
    assert protocol["complete"] is True
    assert protocol["covered_scope_count"] == 0
    assert merged["impacted_files"] == []
    assert merged["total_impacted"] == 0


def test_f001_scope_isolation_traversal_and_flag_injection_faults(tmp_path: Path):
    """F-001 fault injection: _scope_files rejects traversal, flags, directories, and non-existent files."""
    valid_file = tmp_path / "valid_script.py"
    valid_file.write_text("print('test')", encoding="utf-8")
    sub_dir = tmp_path / "sub_dir"
    sub_dir.mkdir()

    # Path traversal outside repository
    with pytest.raises(RuntimeError, match="escapes repository"):
        dispatch_l2._scope_files("../../escape.py", tmp_path)

    # Flag-like token injection
    with pytest.raises(RuntimeError, match="flag-like token"):
        dispatch_l2._scope_files("--injected-flag", tmp_path)

    # Directory token rejection (must be regular file)
    with pytest.raises(RuntimeError, match="does not name an existing repo-local regular file"):
        dispatch_l2._scope_files("sub_dir", tmp_path)

    # Non-existent file token rejection
    with pytest.raises(RuntimeError, match="does not name an existing repo-local regular file"):
        dispatch_l2._scope_files("non_existent_file.py", tmp_path)

    # Control characters injection
    with pytest.raises(RuntimeError, match="control-free string"):
        dispatch_l2._scope_files("valid_script.py\n", tmp_path)

    # Duplicate file tokens rejection
    with pytest.raises(RuntimeError, match="duplicate file token"):
        dispatch_l2._scope_files("valid_script.py valid_script.py", tmp_path)

    # Valid scope resolves cleanly
    resolved = dispatch_l2._scope_files("valid_script.py", tmp_path)
    assert resolved == ["valid_script.py"]


def test_f001_scope_isolation_prompt_test_constraint_injection():
    """F-001 scope isolation: dispatch_l2 must inject TEST SCOPE CONSTRAINT into prompt."""
    res = subprocess.run(
        [
            sys.executable,
            "scripts/dispatch_l2.py",
            "devops-engineer",
            "GATE_DISPATCH_L2_IMPACT_QUERY_HARDENING_20260917",
            "test_scope_isolation_slug",
            "Scope isolation validation",
            "scripts/dispatch_l2.py",
            "--risk",
            "low",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert res.returncode == 0
    command, prompt_path, prompt = _parse_command_and_prompt(res.stdout)
    try:
        assert "TEST SCOPE CONSTRAINT: Limit test execution to declared scope files and related test suites" in prompt
        assert "do NOT scan or run the full 4400+ test repository suite" in prompt
    finally:
        prompt_path.unlink(missing_ok=True)
        lock_file = REPO_ROOT / ".ly_state" / "session" / f"dispatch_l2_role11_test_scope_isolation_slug_{datetime.now().strftime('%Y%m%d')}.lock"
        lock_file.unlink(missing_ok=True)


def test_f001_scope_isolation_predispatch_mutation_fault(tmp_path, monkeypatch):
    """F-001 fault injection: mutation of scoped file during graph collection aborts predispatch."""
    import scripts.dispatch_l2 as dl2

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir(parents=True)
    session_dir = repo_dir / ".ly_state" / "session"
    session_dir.mkdir(parents=True)

    session_id = "test_f001_mutation"

    monkeypatch.setattr(dl2, "GRAPH_TOOL_ROOT", tmp_path)
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    monkeypatch.setattr(dl2, "_scope_files", lambda scope, root: ["target.py"])
    monkeypatch.setattr(dl2, "_is_scope_dirty", lambda root, files: False)
    monkeypatch.setattr(dl2, "_current_commit", lambda root: "abcdef1234567890")
    monkeypatch.setattr(dl2, "_graph_commit", lambda: "abcdef1234567890")

    class FakeProc:
        stdout = "status: abcdef123456 ok"
    monkeypatch.setattr(dl2, "_run_checked", lambda cmd, cwd, timeout: FakeProc())
    monkeypatch.setattr(dl2, "_bounded_impact_query", lambda root, files: ({"summary": "s", "impacted_files": [], "total_impacted": 0, "truncated": False}, {"complete": True, "batch_count": 1}))
    monkeypatch.setattr(dl2, "_graph_file_summary", lambda root, p: ({"summary": "ok"}, False))

    call_count = 0
    def mutating_scope_hashes(root, files):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            return {"target.py": "mutated_hash_9999"}
        return {"target.py": "original_hash_1111"}

    monkeypatch.setattr(dl2, "_scope_content_hashes", mutating_scope_hashes)

    with pytest.raises(RuntimeError, match="scope file content changed during graph evidence collection"):
        dl2.run_graph_predispatch_gate(session_id, "target.py", repo_dir)


def test_f002_16d_boundary_invariants_fault_injection():
    """F-002 fault injection: verify 16-dimension invariant defenses fail closed."""
    # Dim 1: Malformed types
    with pytest.raises(RuntimeError, match="invalid count"):
        dispatch_l2._strict_int("not_a_number", "count")
    with pytest.raises(RuntimeError, match="invalid count"):
        dispatch_l2._strict_int(True, "count")
    with pytest.raises(RuntimeError, match="invalid flag"):
        dispatch_l2._strict_bool("yes", "flag")

    # Dim 2: Invalid I/O path containment
    with pytest.raises(SystemExit) as exc:
        dispatch_l2.ensure_session_containment(Path("../outside_escape.txt"))
    assert exc.value.code == 2

    # Dim 4: Fail-closed exit codes
    with pytest.raises(SystemExit) as exc:
        dispatch_l2.validate_identifier("bad;identifier", "role")
    assert exc.value.code == 2

    # Dim 8: Numeric bounds overflow
    with pytest.raises(RuntimeError, match="invalid ladder_val"):
        dispatch_l2._strict_int(1_000_001, "ladder_val", maximum=1_000_000)

    # Dim 16: Credential leak redaction
    sanitized = dispatch_l2.redact_credentials(
        "Failed connection to https://admin:supersecret@api.omega.quant/v1?token=topsecrettoken"
    )
    assert "supersecret" not in sanitized
    assert "topsecrettoken" not in sanitized
    assert "[REDACTED]" in sanitized


def test_f002_validate_l2_report_sweep_schema_and_boundaries():
    """F-002 boundary documentation: validate_l2_report requires exact heading order and sweep JSON."""
    from scripts.validate_l2_report import _check_required_headings, REMEDIATION_H2, BASELINE_H2

    # Valid baseline headings
    baseline_doc = "# L2 Implementation Report\n\n" + "\n\n".join(f"{h}\nContent" for h in BASELINE_H2)
    ok, errs = _check_required_headings(baseline_doc, remediation_required=False)
    assert ok is True
    assert errs == []

    # Valid remediation headings
    remediation_doc = "# L2 Implementation Report\n\n" + "\n\n".join(f"{h}\nContent" for h in REMEDIATION_H2)
    ok, errs = _check_required_headings(remediation_doc, remediation_required=True)
    assert ok is True
    assert errs == []

    # Remediation missing Root-Cause Architectural Sweep heading
    ok, errs = _check_required_headings(baseline_doc, remediation_required=True)
    assert ok is False
    assert any("missing H2 headings" in e for e in errs)

    # Out of order headings
    swapped = list(REMEDIATION_H2)
    swapped[3], swapped[4] = swapped[4], swapped[3]
    bad_order_doc = "# L2 Implementation Report\n\n" + "\n\n".join(f"{h}\nContent" for h in swapped)
    ok, errs = _check_required_headings(bad_order_doc, remediation_required=True)
    assert ok is False
    assert any("out of order" in e for e in errs)


