#!/usr/bin/env python3
"""Validate OMEGA role-load evidence produced by omega_role_router.py."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSION = ROOT / ".ly_state" / "session"
LOADED_ROLES = SESSION / "loaded_roles.json"


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Missing evidence file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_text(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Missing referenced file: {path}")
    return path.read_text(encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def select_entries(payload: dict, task_type: str | None, role_id: str | None) -> list[dict]:
    entries = payload.get("routes", [])
    if task_type:
        entries = [entry for entry in entries if entry.get("task_type") == task_type]
    if role_id:
        entries = [entry for entry in entries if str(entry.get("role_id")) == role_id]
    return entries


def validate_entry(entry: dict) -> list[str]:
    errors: list[str] = []
    role_file = entry.get("role_file")
    prompt_path = entry.get("prompt_path")
    role_digest = entry.get("role_file_sha256")

    if not role_file:
        errors.append("missing role_file")
    if not prompt_path:
        errors.append("missing prompt_path")
    if not role_digest:
        errors.append("missing role_file_sha256")
    if errors:
        return errors

    role_abs = ROOT / role_file
    prompt_abs = ROOT / prompt_path
    role_text = read_text(role_abs)
    prompt_text = read_text(prompt_abs)
    actual_role_digest = sha256_text(role_text)

    if actual_role_digest != role_digest:
        errors.append(
            f"role checksum mismatch: expected {role_digest}, got {actual_role_digest}"
        )
    if f"ROLE FILE CONTENT BEGIN path={role_file} sha256={role_digest}" not in prompt_text:
        errors.append("prompt missing role content evidence header")
    if role_text.rstrip() not in prompt_text:
        errors.append("prompt missing embedded role file content")

    for skill in entry.get("mandatory_skills", []):
        skill_path = skill.get("path")
        skill_digest = skill.get("sha256")
        if not skill_path or not skill_digest:
            errors.append("mandatory skill entry missing path/sha256")
            continue
        skill_text = read_text(ROOT / skill_path)
        actual_skill_digest = sha256_text(skill_text)
        if actual_skill_digest != skill_digest:
            errors.append(
                f"skill checksum mismatch for {skill_path}: "
                f"expected {skill_digest}, got {actual_skill_digest}"
            )
        if f"SOD SKILL CONTENT BEGIN path={skill_path} sha256={skill_digest}" not in prompt_text:
            errors.append(f"prompt missing skill evidence header for {skill_path}")
        if skill_text.rstrip() not in prompt_text:
            errors.append(f"prompt missing embedded skill content for {skill_path}")

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate OMEGA role-load evidence.")
    parser.add_argument("--task-type", help="Only validate routes for this task type")
    parser.add_argument("--role-id", help="Only validate routes for this role ID")
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Validate only the latest matching route",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = load_json(LOADED_ROLES)
        entries = select_entries(payload, args.task_type, args.role_id)
        if args.latest and entries:
            entries = [entries[-1]]
        if not entries:
            print("[FAIL] No matching role-load evidence", file=sys.stderr)
            return 1

        failed = False
        for index, entry in enumerate(entries, start=1):
            errors = validate_entry(entry)
            label = (
                f"#{index} role={entry.get('role_id')} "
                f"task_type={entry.get('task_type')} prompt={entry.get('prompt_path')}"
            )
            if errors:
                failed = True
                print(f"[FAIL] {label}")
                for error in errors:
                    print(f"  - {error}")
            else:
                print(f"[PASS] {label}")
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    if failed:
        return 1
    print("[PASS] Role-load evidence valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
