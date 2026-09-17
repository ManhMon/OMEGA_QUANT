import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from lint_sod_report_evidence import main


def test_lint_uses_shared_validator(tmp_path, capsys):
    report = tmp_path / "role21_gate_20260725.md"
    report.write_text(
        "## Repo-Local Files Read\nREPO_AGENT_ROOT REPO_SKILL_ROOT\n"
        "## Forbidden Path Scan\n"
        "- .gemini\\antigravity-ide\\scratch\\ag-kit: non-authoritative scan evidence only; no reliance.\n"
        "- .openclaw\\skills: non-authoritative scan evidence only; no reliance.\n"
        "- C:\\Users\\GHC\\.agents: non-authoritative scan evidence only; no reliance.\n"
        "- .codex\\memories: non-authoritative scan evidence only; no reliance.\n",
        encoding="utf-8",
    )
    assert main([str(report), "--gate", "gate_20260725"]) == 0
    assert "PASS" in capsys.readouterr().out
