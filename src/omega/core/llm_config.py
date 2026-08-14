"""Shared alpha LLM configuration resolution."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SUPPORTED_LLM_PROVIDERS = {"mock", "openai-compatible"}
ALPHA_LLM_CONFIG_ENV = "OMEGA_ALPHA_LLM_CONFIG_PATH"


def load_external_alpha_config(repo_root: Path) -> dict[str, Any]:
    config_path = os.environ.get(ALPHA_LLM_CONFIG_ENV)
    if not config_path:
        return {}
    try:
        path = Path(config_path)
        resolved = path.resolve(strict=True)
        if not path.is_absolute() or str(path) != str(resolved) or resolved.is_relative_to(repo_root.resolve()):
            return {}
        config = json.loads(path.read_text(encoding="utf-8"))
        provider = config.get("provider") if isinstance(config, dict) else None
        if not isinstance(config, dict) or (provider is not None and str(provider).strip().lower() not in SUPPORTED_LLM_PROVIDERS):
            return {}
        return config
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, TypeError):
        return {}


def resolve_alpha_llm_config(repo_root: Path, provider_override: str | None = None) -> dict[str, Any]:
    file_config = load_external_alpha_config(repo_root)
    selected = provider_override or file_config.get("provider") or os.environ.get("OMEGA_LLM_PROVIDER")
    if selected is None:
        selected = "openai-compatible" if (file_config.get("api_key") or os.environ.get("OMEGA_LLM_API_KEY")) else "mock"
    provider = str(selected).strip().lower()
    if provider not in SUPPORTED_LLM_PROVIDERS:
        source = "provider" if provider_override is not None else "OMEGA_LLM_PROVIDER"
        raise ValueError(f"Unsupported provider in {source}: {provider}")
    return {
        "provider": provider,
        "api_key": file_config.get("api_key") or os.environ.get("OMEGA_LLM_API_KEY"),
        "base_url": file_config.get("base_url") or os.environ.get("OMEGA_LLM_BASE_URL"),
        "model": file_config.get("model") or os.environ.get("OMEGA_LLM_MODEL", "gpt-4"),
    }


def sanitize_llm_config(config: dict[str, Any]) -> dict[str, Any]:
    return {"provider": config.get("provider"), "base_url": config.get("base_url"), "model": config.get("model"), "api_key_present": bool(config.get("api_key"))}
