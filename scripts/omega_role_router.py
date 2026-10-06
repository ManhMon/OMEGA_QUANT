#!/usr/bin/env python3
"""OMEGA role router for 25-role SOD workflows.

Routes tasks to Ly L1, OpenCode L2, or Codex L3 while injecting the
correct role instruction file and preserving SOD boundaries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[1]
SESSION = ROOT / ".ly_state" / "session"
ROLE_ROUTER = SESSION / "role_router.json"
ROUTING_POLICY = SESSION / "routing_policy.json"
PROMPT_DIR = SESSION / "routing_prompts"
LOADED_ROLES = SESSION / "loaded_roles.json"

TASK_KEYWORDS = {
    "status": ["status", "xong", "done", "gate", "sod", "approved"],
    "planning": ["plan", "kế hoạch", "roadmap", "breakdown", "thiết kế"],
    "audit_security": ["security", "vulnerability", "pentest"],
    "audit_compliance": ["compliance", "pit", "look-ahead", "lookahead"],
    "audit_code": ["audit", "review", "codex", "approve"],
    "architecture": ["architecture", "kiến trúc", "refactor", "design"],
    "implementation_frontend": ["ui", "frontend", "css", "react", "page"],
    "data_pipeline": ["data", "pipeline", "etl", "ingest"],
    "ml_modeling": ["model", "ml", "alpha", "signal", "training"],
    "devops_infra": ["deploy", "ci", "cd", "infra", "docker"],
    "implementation_backend": ["python", "api", "backend", "fix", "implement", "code"],
}

DEFAULT_SKILLS = [
    ".agents/skills/omega-sod/skill.md",
]


@dataclass(frozen=True)
class Route:
    task_type: str
    role_id: str
    role_name: str
    tier: str
    platform: str
    cli: str
    role_file: str
    role_file_sha256: str
    skill_sha256: dict[str, str]
    prompt_path: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required router file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_text(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required instruction file: {path}")
    return path.read_text(encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def classify_task(text: str) -> str:
    lowered = text.lower()
    for task_type, keywords in TASK_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return task_type
    return "implementation_backend"


def select_role(task_type: str, role_override: str | None, policy: dict) -> str:
    if role_override:
        return str(role_override)

    task_policy = policy["task_types"].get(task_type)
    if not task_policy:
        return "9"
    return str(task_policy["primary_roles"][0])


def build_prompt(
    *,
    task: str,
    task_type: str,
    role: dict,
    role_id: str,
    context_files: list[str],
    role_content: str,
    role_sha256: str,
    skill_contents: dict[str, str],
    skill_sha256: dict[str, str],
) -> str:
    platform = role["platform"]
    tier = role["tier"]
    role_file = role["role_file"]
    skills = "\n".join(
        f"- {skill} sha256={skill_sha256[skill]}" for skill in DEFAULT_SKILLS
    )
    context = "\n".join(f"- {path}" for path in context_files) or "- None"
    skill_blocks = "\n\n".join(
        dedent(
            f"""
            SOD SKILL CONTENT BEGIN path={skill} sha256={skill_sha256[skill]}
            {content.rstrip()}
            SOD SKILL CONTENT END path={skill}
            """
        ).strip()
        for skill, content in skill_contents.items()
    )

    if tier == "L3":
        action_contract = dedent(
            """
            L3 READ-ONLY CONTRACT:
            - Do NOT edit production code.
            - Do NOT commit changes.
            - Write an audit report only.
            - Final verdict must be exactly [APPROVED] or [NEEDS_FIX].
            - Include l3_session_id, l3_session_key, audit_report_path,
              final_verdict.
            - Recommended early feedback: run `python scripts/lint_sod_report_evidence.py <report> --gate <gate>`.
              This is advisory and does not replace the final `python scripts/sod_gate_enforcer.py` hard gate.
            """
        ).strip()
    elif tier == "L2":
        action_contract = dedent(
            """
            L2 IMPLEMENTATION CONTRACT:
            - Implement only the assigned scope.
            - Run relevant tests and validation.
            - Do NOT self-approve.
            - Produce implementation summary and handoff for L3 audit.
            - Use headings `## Repo-Local Files Read` and `## Forbidden Path Scan`.
            - Put each forbidden path on its own line with `non-authoritative scan evidence only; no reliance.`
            - Recommended early feedback: run `python scripts/lint_sod_report_evidence.py <report> --gate <gate>`.
              This is advisory and does not replace the final `python scripts/sod_gate_enforcer.py` hard gate.
            """
        ).strip()
    else:
        action_contract = dedent(
            """
            L1 ORCHESTRATION CONTRACT:
            - Coordinate and decide gates.
            - Do not perform L3 audit verdicts.
            - Do not bypass SOD evidence requirements.
            """
        ).strip()

    return dedent(
        f"""
        ROLE ROUTING PROMPT - OMEGA_QUANT SOD v2.1

        ORIGINAL USER REQUEST:
        {task}

        ROUTE:
        - task_type: {task_type}
        - selected_role_id: {role_id}
        - selected_role_name: {role['name']}
        - tier: {tier}
        - platform: {platform}
        - cli: {role['cli']}
        - role_file: {role_file}
        - role_file_sha256: {role_sha256}

        MANDATORY FIRST STEP:
        1. Confirm embedded role instruction checksum: {role_sha256}
        2. Confirm embedded mandatory SOD skill checksum(s):
        {skills}
        3. Apply all role boundaries before doing any work.
        4. Report role_load_evidence with role_file_sha256 in output.

        MINIMAL CONTEXT FILES:
        {context}

        SOD BOUNDARIES:
        - allowed_actions: {', '.join(role['allowed_actions'])}
        - forbidden_actions: {', '.join(role['forbidden_actions'])}

        {action_contract}

        ROLE FILE CONTENT BEGIN path={role_file} sha256={role_sha256}
        {role_content.rstrip()}
        ROLE FILE CONTENT END path={role_file}

        {skill_blocks}

        TASK:
        Execute only the requested role-specific work for the original user
        request. If required context is missing, report missing context instead
        of guessing.
        """
    ).strip() + "\n"


def write_prompt(prompt: str, task_type: str, role_name: str) -> Path:
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = role_name.replace("-", "_")
    prompt_path = PROMPT_DIR / f"{task_type}_{safe_name}.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    return prompt_path


def append_loaded_role(entry: dict) -> None:
    SESSION.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": utc_now(), "routes": []}
    if LOADED_ROLES.is_file():
        payload = load_json(LOADED_ROLES)
        payload.setdefault("routes", [])
        payload["generated_at"] = utc_now()
    payload["routes"].append(entry)
    LOADED_ROLES.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def route_task(
    task: str,
    role_override: str | None,
    context_files: list[str],
) -> Route:
    registry = load_json(ROLE_ROUTER)
    policy = load_json(ROUTING_POLICY)
    task_type = classify_task(task)
    role_id = select_role(task_type, role_override, policy)
    role = registry["roles"].get(role_id)
    if role is None:
        raise ValueError(f"Unknown role_id: {role_id}")

    role_content = read_text(ROOT / role["role_file"])
    role_sha256 = sha256_file(ROOT / role["role_file"])
    skill_contents = {skill: read_text(ROOT / skill) for skill in DEFAULT_SKILLS}
    skill_sha256 = {
        skill: sha256_file(ROOT / skill) for skill in DEFAULT_SKILLS
    }

    prompt = build_prompt(
        task=task,
        task_type=task_type,
        role=role,
        role_id=role_id,
        context_files=context_files,
        role_content=role_content,
        role_sha256=role_sha256,
        skill_contents=skill_contents,
        skill_sha256=skill_sha256,
    )
    prompt_path = write_prompt(prompt, task_type, role["name"])
    append_loaded_role(
        {
            "generated_at": utc_now(),
            "task_type": task_type,
            "role_id": role_id,
            "role_name": role["name"],
            "tier": role["tier"],
            "platform": role["platform"],
            "cli": role["cli"],
            "role_file": role["role_file"],
            "role_file_sha256": role_sha256,
            "prompt_path": str(prompt_path.relative_to(ROOT)),
            "mandatory_skills": [
                {"path": skill, "sha256": digest}
                for skill, digest in skill_sha256.items()
            ],
        }
    )
    return Route(
        task_type=task_type,
        role_id=role_id,
        role_name=role["name"],
        tier=role["tier"],
        platform=role["platform"],
        cli=role["cli"],
        role_file=role["role_file"],
        role_file_sha256=role_sha256,
        skill_sha256=skill_sha256,
        prompt_path=prompt_path,
    )


def render_cli_hint(route: Route) -> str:
    if route.cli == "codex":
        return f"Get-Content {route.prompt_path} | codex exec --full-auto"
    if route.cli == "opencode":
        return f"opencode run --prompt-file {route.prompt_path}"
    return "Ly handles this route directly; no external CLI required."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Route an OMEGA task to a role.")
    parser.add_argument("task", help="Task/request text to classify and route")
    parser.add_argument("--role-id", help="Override selected role ID")
    parser.add_argument(
        "--context-file",
        action="append",
        default=[],
        help="Context file path to include in generated prompt",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print route metadata as JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        route = route_task(args.task, args.role_id, args.context_file)
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    payload = {
        "task_type": route.task_type,
        "role_id": route.role_id,
        "role_name": route.role_name,
        "tier": route.tier,
        "platform": route.platform,
        "cli": route.cli,
        "role_file": route.role_file,
        "role_file_sha256": route.role_file_sha256,
        "prompt_path": str(route.prompt_path.relative_to(ROOT)),
        "loaded_roles_path": str(LOADED_ROLES.relative_to(ROOT)),
        "cli_hint": render_cli_hint(route),
    }

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("OMEGA Role Route")
        print("=" * 60)
        for key, value in payload.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
