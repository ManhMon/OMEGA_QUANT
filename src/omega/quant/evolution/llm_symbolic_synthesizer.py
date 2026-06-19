"""LLM-in-the-Loop Symbolic Synthesizer.

Generates and validates new alpha factor formulas using LLM feedback.
Point-in-Time safe: Enforces strict temporal constraints on generated features.

Security: API keys from env only, never logged. Deterministic cache with prompt hashing.
Formula safety: strict prefix syntax, allowed operators, depth/lookback caps.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Lazy import to avoid circular dependency issues
from omega.quant.evolution.genetic_programming import GPNode

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def generate(self, prompt: str) -> List[str]:
        """Generate formulas from prompt. Returns list of formula strings."""
        pass


class MockProvider(LLMProvider):
    """Mock provider for offline/testing operation."""
    
    def generate(self, prompt: str) -> List[str]:
        """Return hardcoded mock formulas."""
        return [
            "decay_linear(ret_1d, 5)",
            "ts_rank(volume, 20)",
            "div(ts_std(close, 20), ts_mean(volume, 10))"
        ]


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI-compatible API provider with security controls."""
    
    def __init__(self, api_key: str, model: str, base_url: Optional[str] = None):
        """
        Initialize provider.
        
        Args:
            api_key: API key (from env only, never logged)
            model: Model name
            base_url: Optional API base URL
        """
        # Never log the API key
        self._api_key = api_key
        self.model = model
        self.base_url = base_url or "https://api.openai.com/v1"
        logger.info(
            "OpenAICompatibleProvider initialized: model=%s base_url=%s",
            model, base_url
        )
    
    def generate(self, prompt: str) -> List[str]:
        """
        Generate formulas via OpenAI-compatible API.
        
        Returns:
            List of formula strings
        """
        try:
            import requests
        except ImportError:
            logger.error("requests library required for OpenAI provider")
            return []
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an expert quantitative researcher."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            # Parse formulas from response (one per line)
            formulas = [
                line.strip() 
                for line in content.strip().split('\n') 
                if line.strip() and not line.strip().startswith('#')
            ]
            
            logger.info("OpenAI provider generated %d formulas", len(formulas))
            return formulas[:10]  # Cap at 10 formulas for safety
            
        except Exception as e:
            logger.error("OpenAI API call failed: %s", str(e))
            return []


class FormulaCache:
    """Deterministic on-disk cache for LLM formula generation with versioning."""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize cache.
        
        Args:
            cache_dir: Cache directory (default: .ly_state/session/llm_cache/)
        """
        if cache_dir is None:
            repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
            cache_dir = repo_root / ".ly_state" / "session" / "llm_cache"
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("FormulaCache initialized: %s", self.cache_dir)
    
    def _hash_prompt(self, prompt: str, prompt_version: str = "v1") -> str:
        """
        Hash prompt for cache key with version namespace.
        
        Args:
            prompt: Prompt string (secrets must be stripped before calling)
            prompt_version: Prompt version for cache namespace isolation
        
        Returns:
            Hex digest of SHA256 hash including version prefix
        """
        # Include version in hash to isolate cache namespaces
        versioned_content = f"VERSION:{prompt_version}\n{prompt}"
        return hashlib.sha256(versioned_content.encode('utf-8')).hexdigest()
    
    def get(self, prompt: str, prompt_version: str = "v1") -> Optional[List[str]]:
        """
        Get cached formulas for prompt and version.
        
        Args:
            prompt: Prompt string (secrets must be stripped)
            prompt_version: Prompt version for cache namespace
        
        Returns:
            Cached formulas or None if not found
        """
        cache_key = self._hash_prompt(prompt, prompt_version)
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
            
            # Verify version matches (defense in depth)
            if data.get("prompt_version") != prompt_version:
                logger.warning(
                    "Cache version mismatch: expected %s, got %s, ignoring cache",
                    prompt_version,
                    data.get("prompt_version")
                )
                return None
            
            logger.debug("Cache hit: %s (version=%s)", cache_key[:16], prompt_version)
            return data.get("formulas", [])
        except Exception as e:
            logger.warning("Cache read failed: %s", e)
            return None
    
    def set(self, prompt: str, formulas: List[str], prompt_version: str = "v1") -> None:
        """
        Cache formulas for prompt and version.
        
        Args:
            prompt: Prompt string (secrets must be stripped)
            formulas: List of formula strings (no secrets)
            prompt_version: Prompt version for cache namespace
        """
        cache_key = self._hash_prompt(prompt, prompt_version)
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        try:
            # Never cache secrets - only cache the formulas output
            data = {
                "prompt_hash": cache_key,
                "prompt_version": prompt_version,
                "formulas": formulas,
                "timestamp": pd.Timestamp.now().isoformat()
            }
            
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug("Cache write: %s (version=%s)", cache_key[:16], prompt_version)
        except Exception as e:
            logger.warning("Cache write failed: %s", e)


class FormulaSafetyParser:
    """
    Strict formula safety parser.
    
    Enforces:
    - Only prefix syntax (function calls, no infix)
    - Allowed operators and terminals
    - Depth cap
    - Lookback range [2, 60]
    - Max formulas cap
    - Rejects unknown terminals, operators, trailing tokens
    """
    
    def __init__(
        self,
        allowed_terminals: List[str],
        allowed_unary: List[str],
        allowed_binary: List[str],
        allowed_ts: List[str],
        max_depth: int = 5,
        min_lookback: int = 2,
        max_lookback: int = 60,
        max_formulas: int = 10
    ):
        self.allowed_terminals = set(allowed_terminals)
        self.allowed_unary = set(allowed_unary)
        self.allowed_binary = set(allowed_binary)
        self.allowed_ts = set(allowed_ts)
        self.max_depth = max_depth
        self.min_lookback = min_lookback
        self.max_lookback = max_lookback
        self.max_formulas = max_formulas
    
    def validate_formula(self, formula: str) -> Tuple[bool, str]:
        """
        Validate formula against safety rules.
        
        Args:
            formula: Formula string to validate
        
        Returns:
            (is_valid, error_message) tuple
        """
        # Check for infix operators (not in function call context)
        # Infix pattern: token operator token (not inside function parens)
        if re.search(r'\w+\s*[\+\-\*/]\s*\w+', formula):
            return False, "Infix operators not allowed (use prefix syntax)"
        
        # Tokenize
        tokens = self._tokenize(formula)
        
        if not tokens:
            return False, "Empty formula"
        
        # Parse and validate tree
        try:
            consumed_idx, depth, lookbacks = self._validate_tree(tokens, 0, 0)
            
            # Check that all tokens were consumed
            if consumed_idx < len(tokens):
                remaining = tokens[consumed_idx:]
                return False, f"Unexpected trailing tokens: {remaining}"
            
            if depth > self.max_depth:
                return False, f"Depth {depth} exceeds max {self.max_depth}"
            
            # Validate lookback ranges
            for lb in lookbacks:
                if lb < self.min_lookback or lb > self.max_lookback:
                    return False, f"Lookback {lb} outside range [{self.min_lookback}, {self.max_lookback}]"
            
            return True, ""
            
        except ValueError as e:
            return False, str(e)
    
    def _tokenize(self, formula: str) -> List[str]:
        """Tokenize formula string."""
        pattern = r'[a-zA-Z_]\w*|\d+(?:\.\d+)?|[(),]'
        return re.findall(pattern, formula.replace(" ", ""))
    
    def _validate_tree(
        self, 
        tokens: List[str], 
        index: int, 
        depth: int
    ) -> Tuple[int, int, List[int]]:
        """
        Recursively validate expression tree.
        
        Returns:
            (consumed_index, max_depth, lookback_values) tuple
            consumed_index is the index of the first token after this expression
        
        Raises:
            ValueError if validation fails
        """
        if index >= len(tokens):
            raise ValueError("Unexpected end of expression")
        
        token = tokens[index]
        
        # Check for parenthesized expression (not allowed - must be prefix)
        if token == '(':
            raise ValueError("Parenthesized infix expressions not allowed")
        
        # Function call: func(args)
        if index + 1 < len(tokens) and tokens[index + 1] == '(':
            func_name = token
            
            # Check if function is allowed
            all_ops = (
                self.allowed_unary | 
                self.allowed_binary | 
                self.allowed_ts |
                {'add', 'sub', 'mul', 'div'}  # Prefix aliases
            )
            
            if func_name not in all_ops:
                raise ValueError(f"Unknown operator: {func_name}")
            
            # Parse arguments
            curr_idx = index + 2
            args = []
            lookbacks = []
            
            while curr_idx < len(tokens) and tokens[curr_idx] != ')':
                if tokens[curr_idx] == ',':
                    curr_idx += 1
                    continue
                
                # Check if this is a lookback parameter (for time-series ops)
                if tokens[curr_idx].isdigit() and func_name in self.allowed_ts:
                    lookback_val = int(tokens[curr_idx])
                    lookbacks.append(lookback_val)
                    curr_idx += 1
                else:
                    # Recursive validation
                    consumed, arg_depth, arg_lookbacks = self._validate_tree(tokens, curr_idx, depth + 1)
                    args.append(arg_depth)
                    lookbacks.extend(arg_lookbacks)
                    # Move to the next token after this arg
                    curr_idx = consumed
            
            if curr_idx >= len(tokens) or tokens[curr_idx] != ')':
                raise ValueError(f"Expected ')' for function {func_name}")
            
            max_arg_depth = max(args) if args else 0
            # Return index after the closing ')'
            return curr_idx + 1, max(depth + 1, max_arg_depth), lookbacks
        
        # Terminal: variable or constant
        if token.isdigit() or '.' in token:
            # Constant - consume one token
            return index + 1, depth, []
        
        if token in self.allowed_terminals:
            # Variable - consume one token
            return index + 1, depth, []
        
        raise ValueError(f"Unknown terminal: {token}")
    
    def _skip_subtree(self, tokens: List[str], index: int) -> int:
        """Skip over a subtree and return index after it."""
        token = tokens[index]
        
        if index + 1 < len(tokens) and tokens[index + 1] == '(':
            # Function call - skip to matching )
            depth = 1
            curr_idx = index + 2
            while curr_idx < len(tokens) and depth > 0:
                if tokens[curr_idx] == '(':
                    depth += 1
                elif tokens[curr_idx] == ')':
                    depth -= 1
                curr_idx += 1
            return curr_idx
        else:
            # Terminal - just move past it
            return index + 1
    
    def validate_batch(self, formulas: List[str]) -> List[str]:
        """
        Validate batch of formulas and return only valid ones.
        
        Args:
            formulas: List of formula strings
        
        Returns:
            List of valid formulas (capped at max_formulas)
        """
        valid = []
        
        for formula in formulas[:self.max_formulas]:
            is_valid, error = self.validate_formula(formula)
            if is_valid:
                valid.append(formula)
                logger.debug("Formula valid: %s", formula)
            else:
                logger.warning("Formula rejected: %s (reason: %s)", formula, error)
        
        return valid


class LLMSymbolicSynthesizer:
    """
    Orchestrates LLM-based formula generation, parsing, and validation.
    
    Security features:
    - API key from env only, never logged
    - Deterministic cache (prompt hash with version namespace)
    - Strict formula safety parser
    - Default offline/mock mode
    
    Staged search improvements (v2):
    - Prompt versioning for cache isolation
    - Formula deduplication via normalization
    - Rejection taxonomy tracking
    - Configurable candidate budget
    - Richer stats/evidence
    """

    def __init__(
        self, 
        use_mock: bool = True, 
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        prompt_version: str = "vn_alpha_search_v2",
        max_candidates: Optional[int] = None
    ):
        """
        Initialize synthesizer.
        
        Args:
            use_mock: Use mock provider (default True for safety)
            provider: Provider type ('mock' or 'openai-compatible'), overrides use_mock
            api_key: API key (DEPRECATED - use env var OMEGA_LLM_API_KEY)
            prompt_version: Prompt template version (default: vn_alpha_search_v2)
            max_candidates: Max candidate formulas (default: OMEGA_LLM_MAX_CANDIDATES env or 10)
        """
        # Valid operators supported by GPNode._execute_tree
        self.unary_ops = ['abs', 'log', 'sqrt', 'exp', 'sigmoid', 'rank', 'neg']
        self.binary_ops = ['+', '-', '*', '/', 'max', 'min']
        self.ts_ops = ['ts_std', 'ts_mean', 'ts_rank', 'decay_linear']
        
        # Prompt version for cache namespace isolation
        self.prompt_version = prompt_version
        
        # Max candidates from env or parameter
        if max_candidates is None:
            max_candidates = int(os.environ.get('OMEGA_LLM_MAX_CANDIDATES', '10'))
        self.max_candidates = max_candidates
        
        # Initialize safety parser
        allowed_terminals = [
            'close', 'open', 'high', 'low', 'volume',
            'ret_1d', 'ret_5d', 'ret_20d'
        ]
        self.safety_parser = FormulaSafetyParser(
            allowed_terminals=allowed_terminals,
            allowed_unary=self.unary_ops,
            allowed_binary=self.binary_ops,
            allowed_ts=self.ts_ops,
            max_depth=5,
            min_lookback=2,
            max_lookback=60,
            max_formulas=max_candidates
        )
        
        # Initialize cache
        self.cache = FormulaCache()
        
        # Initialize provider based on configuration
        self.provider = self._init_provider(use_mock, provider, api_key)
        
        logger.info(
            "LLMSymbolicSynthesizer initialized: prompt_version=%s max_candidates=%d",
            self.prompt_version,
            self.max_candidates
        )
    
    def _init_provider(
        self, 
        use_mock: bool, 
        provider: Optional[str],
        api_key: Optional[str]
    ) -> LLMProvider:
        """
        Initialize LLM provider with security controls.
        
        Provider selection priority:
        1. Explicit provider argument
        2. OMEGA_LLM_PROVIDER env var
        3. use_mock flag (default True)
        
        Security:
        - API key from env only (OMEGA_LLM_API_KEY)
        - Real provider disabled unless explicitly enabled
        - Never log API keys
        """
        # Determine provider type
        provider_type = provider or os.environ.get('OMEGA_LLM_PROVIDER', 'mock' if use_mock else 'mock')
        
        if provider_type == 'mock':
            logger.info("Using MockProvider (offline mode)")
            return MockProvider()
        
        if provider_type == 'openai-compatible':
            # Real provider requires explicit env configuration
            env_api_key = os.environ.get('OMEGA_LLM_API_KEY')
            
            if not env_api_key:
                logger.warning(
                    "OpenAI provider requested but OMEGA_LLM_API_KEY not set. "
                    "Falling back to MockProvider."
                )
                return MockProvider()
            
            # Warn if api_key passed directly (deprecated)
            if api_key is not None:
                logger.warning(
                    "Passing api_key directly is deprecated and ignored. "
                    "Use OMEGA_LLM_API_KEY env var."
                )
            
            # Get model and base_url from env
            model = os.environ.get('OMEGA_LLM_MODEL', 'gpt-4')
            base_url = os.environ.get('OMEGA_LLM_BASE_URL')
            
            logger.info("Using OpenAICompatibleProvider with model=%s", model)
            return OpenAICompatibleProvider(
                api_key=env_api_key,
                model=model,
                base_url=base_url
            )
        
        logger.warning(
            "Unknown provider type '%s'. Valid: 'mock', 'openai-compatible'. "
            "Falling back to MockProvider.",
            provider_type
        )
        return MockProvider()

    def generate_prompt(
        self,
        top_features: List[Tuple[str, float]],
        correlation_clusters: List[List[str]],
        prior_failure_stats: Optional[Dict[str, float]] = None,
        bad_motifs: Optional[Set[str]] = None
    ) -> str:
        """
        Generate a prompt instructing the LLM to generate new formulas.
        
        Security: This prompt does NOT contain API keys or credentials, safe to cache.
        
        Args:
            top_features: List of (feature_name, IC) tuples
            correlation_clusters: List of correlated feature groups
            prior_failure_stats: Optional aggregate stats from prior supervised validation failures
                                (e.g., {"median_test_ic": 0.02, "median_dsr": -0.1})
                                PIT-safe: only aggregate metrics, NO row-level label data
            bad_motifs: Optional set of failed formula patterns to avoid
        
        Returns:
            Prompt string for LLM formula generation
        """
        if self.prompt_version == "vn_alpha_search_v3_closed_loop":
            return self._generate_prompt_v3(top_features, correlation_clusters, prior_failure_stats, bad_motifs)
        elif self.prompt_version == "vn_alpha_search_v2":
            return self._generate_prompt_v2(top_features, correlation_clusters, prior_failure_stats)
        else:
            # Legacy v1 prompt (backward compatibility)
            return self._generate_prompt_v1(top_features, correlation_clusters)
    
    def _generate_prompt_v1(
        self,
        top_features: List[Tuple[str, float]],
        correlation_clusters: List[List[str]]
    ) -> str:
        """Legacy v1 prompt template."""
        top_feats_str = "\n".join(
            [f"- {name}: IC = {ic:.4f}" for name, ic in top_features[:10]])
        clusters_str = "\n".join(
            [f"- Group: {', '.join(c[:5])}" for c in correlation_clusters[:5]])

        prompt = f"""
You are an expert quantitative research AI specialized in Vietnamese stocks (VNIndex).
Your task is to propose 3 new mathematical alpha factors to improve model predictions.

Here are the top-performing features currently:
{top_feats_str}

Here are clusters of highly correlated features that you should avoid duplicating:
{clusters_str}

Available Primitives:
- OHLCV Variables: close, open, high, low, volume, ret_1d, ret_5d
- Unary Operators: abs(x), log(x), sqrt(x), sigmoid(x), rank(x), neg(x)
- Binary Operators: add(x, y), sub(x, y), mul(x, y), div(x, y), max(x, y), min(x, y)
- Time-series Operators: ts_mean(x, d), ts_std(x, d), ts_rank(x, d),
  decay_linear(x, d)  (d = lookback integer, 2 ≤ d ≤ 60)

Rules:
1. ONLY use prefix function syntax (e.g. add(x, y), ts_mean(close, 20)).
   DO NOT use infix operators like x + y.
2. The formula must be strictly PIT-compliant: do not reference future information.
3. Keep the depth of the tree under 5.

Response Format:
Return exactly 3 lines, each containing only the formula. Example:
add(ts_mean(close, 20), ts_rank(volume, 10))
sub(ret_1d, decay_linear(ret_5d, 5))
div(ts_std(close, 15), ts_mean(volume, 20))
"""
        return prompt
    
    def _generate_prompt_v2(
        self,
        top_features: List[Tuple[str, float]],
        correlation_clusters: List[List[str]],
        prior_failure_stats: Optional[Dict[str, float]] = None
    ) -> str:
        """
        V2 prompt template: Vietnamese market context + supervised failure guidance.
        
        PIT-safe: prior_failure_stats contains only AGGREGATE metrics (median IC, DSR)
        from past supervised validation runs, NOT row-level label data.
        """
        top_feats_str = "\n".join(
            [f"- {name}: IC = {ic:.4f}" for name, ic in top_features[:10]])
        clusters_str = "\n".join(
            [f"- Group: {', '.join(c[:5])}" for c in correlation_clusters[:5]])
        
        # Aggregate failure context (PIT-safe: no label leakage)
        failure_context = ""
        if prior_failure_stats:
            train_ic = prior_failure_stats.get("median_train_ic", 0.0)
            dsr = prior_failure_stats.get("median_dsr", 0.0)
            failure_context = f"""
Previous iteration aggregate performance (supervised validation):
- Median Train IC: {train_ic:.4f} (target: >0.05 for meaningful signal)
- Median DSR: {dsr:.3f} (target: >0.5 for statistical significance)

Guidance: Prior formulas showed weak predictive power. Focus on Vietnamese market-specific
patterns such as momentum reversal (short-term overreaction), liquidity effects (volume
divergence), and volatility regimes (VIX-like indicators from rolling variance).
"""
        
        prompt = f"""
You are an expert quantitative researcher specializing in Vietnamese equity alpha factors.
Target market: VNIndex (Ho Chi Minh Stock Exchange), a frontier market with high retail
participation, T+2 settlement, daily price limits (±7%), and frequent liquidity gaps.

Task: Generate {self.max_candidates} NOVEL mathematical alpha formulas that exploit Vietnamese
market microstructure inefficiencies.

Current top features:
{top_feats_str}

Avoid these correlated feature clusters (redundant signals):
{clusters_str}
{failure_context}

Available Primitives:
- OHLCV: close, open, high, low, volume, ret_1d, ret_5d, ret_20d
- Unary: abs(x), log(x), sqrt(x), exp(x), sigmoid(x), rank(x), neg(x)
- Binary: add(x,y), sub(x,y), mul(x,y), div(x,y), max(x,y), min(x,y)
- Time-series: ts_mean(x,d), ts_std(x,d), ts_rank(x,d), decay_linear(x,d)
  where d = lookback days, 2 ≤ d ≤ 60

STRICT CONSTRAINTS:
1. PREFIX SYNTAX ONLY: mul(a, b) NOT a * b. Formulas with infix operators will be REJECTED.
2. PIT-COMPLIANCE: No future data. Only use past/current values via time-series operators.
3. DEPTH LIMIT: Max tree depth = 5 levels.
4. LOOKBACK RANGE: d must be in [2, 60] days.
5. NO TRAILING TOKENS: Each line must be exactly one complete formula.

Vietnamese Market Alpha Ideas (examples, DO NOT copy verbatim):
- Momentum reversal: sub(ts_rank(ret_1d, 5), ts_rank(ret_5d, 20))
- Liquidity divergence: div(ts_std(volume, 10), ts_mean(volume, 20))
- Volatility regime: mul(ts_std(close, 20), rank(volume))
- Price-volume correlation: decay_linear(mul(ret_1d, rank(volume)), 10)

Response Format:
Return EXACTLY {self.max_candidates} lines, each containing ONLY the formula (no explanations).
Example:
sub(ts_rank(ret_1d, 5), decay_linear(ret_5d, 10))
div(ts_std(close, 20), add(ts_mean(volume, 10), abs(ret_1d)))
mul(rank(volume), sub(close, ts_mean(close, 20)))
"""
        return prompt
    
    def _generate_prompt_v3(
        self,
        top_features: List[Tuple[str, float]],
        correlation_clusters: List[List[str]],
        prior_failure_stats: Optional[Dict[str, float]] = None,
        bad_motifs: Optional[Set[str]] = None
    ) -> str:
        """
        V3 prompt template: Closed-loop iterative search with failure feedback.
        
        Enhancements over v2:
        - Stronger emphasis on learning from aggregate failure patterns
        - Explicit avoidance of failed motifs and weak patterns
        - More aggressive novelty requirements
        - Iterative search context (this is iteration N of M)
        - Bad motif blacklist from failed formulas
        
        PIT-safe: prior_failure_stats contains only AGGREGATE metrics (median IC, DSR)
        from past iterations, NOT row-level label data. bad_motifs are pattern strings only.
        """
        top_feats_str = "\n".join(
            [f"- {name}: IC = {ic:.4f}" for name, ic in top_features[:10]])
        clusters_str = "\n".join(
            [f"- Group: {', '.join(c[:5])}" for c in correlation_clusters[:5]])
        
        # Enhanced failure context with learning guidance
        failure_context = ""
        if prior_failure_stats:
            train_ic = prior_failure_stats.get("median_train_ic", 0.0)
            mean_ic = prior_failure_stats.get("mean_train_ic", 0.0)
            dsr = prior_failure_stats.get("median_dsr", 0.0)
            mean_dsr = prior_failure_stats.get("mean_dsr", 0.0)
            
            # Determine failure severity
            ic_weak = train_ic < 0.02
            dsr_negative = dsr < 0.0
            
            failure_severity = "CRITICAL" if (ic_weak and dsr_negative) else "MODERATE" if ic_weak else "MINOR"
            
            failure_context = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ PRIOR ITERATION FEEDBACK - {failure_severity} FAILURE DETECTED                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

Previous iteration aggregate performance (train-only supervised metrics):
- Median Train IC: {train_ic:.4f} (mean: {mean_ic:.4f}) [target: >0.05 for deployment]
- Median DSR: {dsr:.3f} (mean: {mean_dsr:.3f}) [target: >0.5 for significance]

╔══════════════════════════════════════════════════════════════════════════════╗
║ LEARNING DIRECTIVE: Your prior formulas FAILED. Change your approach.       ║
╚══════════════════════════════════════════════════════════════════════════════╝

What went wrong (inferred from aggregate stats):
"""
            
            if ic_weak:
                failure_context += f"""
• WEAK SIGNAL: IC={train_ic:.4f} indicates formulas have almost no predictive power
  → Prior formulas likely too simple, too correlated with existing features, or
    mechanically flawed (constant output, excessive NaN, or look-ahead bias)
  → MUST try fundamentally different factor classes
"""
            
            if dsr_negative:
                failure_context += f"""
• NEGATIVE DSR: DSR={dsr:.3f} means risk-adjusted returns are LOSING money
  → Signal may be correct but too noisy, or directionally inverted
  → Consider: (1) invert the sign, (2) add smoothing/filtering, (3) use different lookbacks
"""
            
            if not ic_weak and not dsr_negative:
                failure_context += f"""
• BORDERLINE PERFORMANCE: Signal exists but too weak for production deployment
  → Try combining successful patterns with complementary signals
  → Increase signal strength via nonlinear transforms or regime conditioning
"""
            
            failure_context += f"""

MANDATORY NOVELTY REQUIREMENTS for this iteration:
1. DO NOT repeat formula structures from prior iterations (they already failed)
2. AVOID these weak patterns:
   - Simple rolling means/stds without cross-sectional normalization
   - Momentum factors without mean reversion components
   - Volume indicators without price confirmation
3. EXPLORE new factor classes:
   - Cross-sectional rank interactions: rank(A) - rank(B)
   - Nonlinear regime switches: A if condition else B patterns
   - Multi-timeframe divergences: short-term vs long-term indicator deltas
   - Volatility-adjusted signals: factor / ts_std(factor, d)

Vietnamese Market Failure Modes (avoid these):
- Liquidity traps: Using volume on illiquid names creates false signals
- Price limit effects: Momentum breaks at ±7% daily limits
- T+2 settlement lag: Signals must account for 2-day execution delay
"""
            
            # Add bad motif blacklist if available
            if bad_motifs and len(bad_motifs) > 0:
                motifs_list = "\n   - ".join(sorted(list(bad_motifs))[:10])  # Show top 10
                failure_context += f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ BAD MOTIF BLACKLIST - FAILED PATTERNS FROM PRIOR ITERATIONS                 ║
╚══════════════════════════════════════════════════════════════════════════════╝

The following formula patterns have consistently FAILED in prior iterations.
DO NOT use these patterns or close variations:
   - {motifs_list}

These patterns produced low IC, high NaN ratios, or constant outputs.
You MUST explore fundamentally different approaches.
"""
        else:
            # First iteration - no prior failure context
            failure_context = """
This is the FIRST iteration. Generate diverse candidates across multiple factor classes:
- Momentum/reversal
- Liquidity/volume
- Volatility regime
- Price-volume divergence
- Cross-sectional ranking
"""
        
        prompt = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ CLOSED-LOOP ITERATIVE ALPHA SEARCH - Vietnamese Equity Market               ║
╚══════════════════════════════════════════════════════════════════════════════╝

MISSION: Generate {self.max_candidates} NOVEL alpha formulas that exploit VNIndex microstructure.
This is an ITERATIVE SEARCH. Learn from aggregate failure patterns and avoid repetition.

Market: VNIndex (Ho Chi Minh Stock Exchange)
Characteristics: Frontier market, high retail participation, T+2 settlement, ±7% daily limits,
                 frequent liquidity gaps, limit-lock manipulation, foreign ownership caps

Current top features (DO NOT duplicate these):
{top_feats_str}

Avoid these correlated clusters (redundant signals):
{clusters_str}
{failure_context}

╔══════════════════════════════════════════════════════════════════════════════╗
║ AVAILABLE PRIMITIVES                                                        ║
╚══════════════════════════════════════════════════════════════════════════════╝

OHLCV Terminals: close, open, high, low, volume, ret_1d, ret_5d, ret_20d

Operators:
• Unary: abs(x), log(x), sqrt(x), exp(x), sigmoid(x), rank(x), neg(x)
• Binary: add(x,y), sub(x,y), mul(x,y), div(x,y), max(x,y), min(x,y)
• Time-series: ts_mean(x,d), ts_std(x,d), ts_rank(x,d), decay_linear(x,d)
  where d = lookback days in range [2, 60]

╔══════════════════════════════════════════════════════════════════════════════╗
║ STRICT CONSTRAINTS (VIOLATIONS → AUTOMATIC REJECTION)                       ║
╚══════════════════════════════════════════════════════════════════════════════╝

1. PREFIX SYNTAX ONLY: mul(a, b) NOT a * b. No infix operators.
2. PIT-COMPLIANCE: No future data. Time-series ops look backward only.
3. DEPTH LIMIT: Max tree depth = 5 levels.
4. LOOKBACK RANGE: d ∈ [2, 60] days.
5. NO TRAILING TOKENS: Each line = exactly one complete formula.
6. NO CREDENTIALS: Do not include API keys or system commands.

╔══════════════════════════════════════════════════════════════════════════════╗
║ NOVELTY EXAMPLES (use as inspiration, DO NOT copy verbatim)                 ║
╚══════════════════════════════════════════════════════════════════════════════╝

Vietnamese-specific patterns:
• Momentum mean-reversion: sub(ts_rank(ret_1d, 5), decay_linear(ts_rank(ret_5d, 20), 10))
• Liquidity regime: div(rank(volume), add(ts_std(volume, 20), abs(ret_1d)))
• Volatility breakout: mul(sub(ts_std(close, 5), ts_std(close, 20)), rank(volume))
• Price-volume divergence: sub(ts_rank(close, 10), ts_rank(volume, 10))
• Cross-sectional volatility: div(ret_1d, ts_std(ret_1d, 20))

╔══════════════════════════════════════════════════════════════════════════════╗
║ RESPONSE FORMAT                                                             ║
╚══════════════════════════════════════════════════════════════════════════════╝

Return EXACTLY {self.max_candidates} lines. Each line contains ONLY the formula (no explanations).
Do NOT number the lines. Do NOT add comments. One formula per line.

Example response:
sub(ts_rank(ret_1d, 5), decay_linear(ret_5d, 10))
div(ts_std(close, 20), add(ts_mean(volume, 10), abs(ret_1d)))
mul(rank(volume), sub(close, ts_mean(close, 20)))
"""
        return prompt

    def normalize_formula(self, formula_str: str) -> str:
        """
        Normalize formula for deduplication.
        
        Removes whitespace and applies canonical formatting so that
        semantically identical formulas are detected as duplicates.
        
        Args:
            formula_str: Raw formula string
        
        Returns:
            Normalized formula string
        """
        # Remove all whitespace
        normalized = formula_str.replace(" ", "").replace("\t", "").replace("\n", "")
        # Lowercase function names for case-insensitive comparison
        # (terminals like 'close' stay lowercase, operators are already lowercase)
        return normalized.lower()
    
    def tokenize(self, formula_str: str) -> List[str]:
        """Tokenize formula string into components."""
        # Split words, numbers, parentheses, commas, and operators
        pattern = r'[a-zA-Z_]\w*|\d+(?:\.\d+)?|[(),\+\-\*/]'
        return re.findall(pattern, formula_str.replace(" ", ""))

    def parse_formula(self, formula_str: str) -> GPNode:
        """Parse formula string into GPNode expression tree recursively."""
        tokens = self.tokenize(formula_str)
        if not tokens:
            raise ValueError("Empty formula string")

        node, idx = self._parse_recursive(tokens, 0)
        if idx < len(tokens):
            raise ValueError(f"Unexpected trailing tokens: {tokens[idx:]}")
        return node

    def _parse_recursive(self, tokens: List[str], index: int) -> Tuple[GPNode, int]:
        if index >= len(tokens):
            raise ValueError("Unexpected end of expression")

        token = tokens[index]

        # Handle parenthesized infix binary expression: (expr op expr)
        if token == '(':
            left, next_idx = self._parse_recursive(tokens, index + 1)
            if next_idx >= len(tokens):
                raise ValueError("Expected operator or closing parenthesis")
            op = tokens[next_idx]
            if op in ['+', '-', '*', '/']:
                right, next_idx2 = self._parse_recursive(tokens, next_idx + 1)
                if next_idx2 >= len(tokens) or tokens[next_idx2] != ')':
                    raise ValueError(f"Expected ')' at index {next_idx2}")
                return GPNode(operator=op, children=[left, right]), next_idx2 + 1
            else:
                if tokens[next_idx] != ')':
                    raise ValueError(f"Expected ')' at index {next_idx}")
                return left, next_idx + 1

        # Handle function call: func(args)
        if index + 1 < len(tokens) and tokens[index + 1] == '(':
            func_name = token
            curr_idx = index + 2
            args = []
            while curr_idx < len(tokens) and tokens[curr_idx] != ')':
                arg, curr_idx = self._parse_recursive(tokens, curr_idx)
                args.append(arg)
                if curr_idx < len(tokens) and tokens[curr_idx] == ',':
                    curr_idx += 1

            if curr_idx >= len(tokens) or tokens[curr_idx] != ')':
                raise ValueError(f"Expected ')' for function {func_name}")

            # Map to standard GPNode operator names
            op_mapping = {
                'add': '+', 'sub': '-', 'mul': '*', 'div': '/',
                'max': 'max', 'min': 'min'
            }
            op = op_mapping.get(func_name, func_name)

            return GPNode(operator=op, children=args), curr_idx + 1

        # Terminal node: variable or constant
        return GPNode(operator='terminal', value=token), index + 1

    def validate_expression(
        self, node: GPNode, features: Dict[str, np.ndarray]
    ) -> bool:
        """
        Verify the expression compiles, executes, has variance, and no look-ahead.
        """
        try:
            # Create a mock GPIndividual to evaluate the tree
            from omega.quant.evolution.genetic_programming import (
                GPIndividual,
                GeneticProgrammingConfig,
            )
            ind = GPIndividual(tree=node)
            cfg = GeneticProgrammingConfig(min_observations=10)

            # Create dummy target
            first_feat = next(iter(features.values()))
            target = np.random.randn(len(first_feat))

            ind.evaluate(features, target, [], cfg)

            # Check if fitness is valid
            if ind.fitness == -np.inf:
                return False

            # Look-ahead check: verify depth limits and only valid terminals.
            terminals = self._collect_terminals(node)
            for t in terminals:
                if t not in features and not self._is_number(t):
                    return False

            return True
        except Exception as e:
            logger.warning(f"Expression validation failed: {e}")
            return False

    def _collect_terminals(self, node: GPNode) -> List[str]:
        if not node.children:
            return [node.value] if node.value else []
        out = []
        for c in node.children:
            out.extend(self._collect_terminals(c))
        return out

    def _is_number(self, s: str) -> bool:
        try:
            float(s)
            return True
        except ValueError:
            return False

    def execute_node_grouped(
        self,
        node: GPNode,
        panel: pd.DataFrame,
        feat_cols: List[str],
        ticker_col: str = "ticker",
        date_col: str = "date",
    ) -> np.ndarray:
        """
        Execute a GPNode tree per-ticker (grouped execution) for PIT safety.
        
        Time-series operators (ts_mean, ts_std, ts_rank, decay_linear) must
        operate within each ticker's sorted date sequence, NOT across a flattened
        cross-ticker array. This prevents look-ahead bias where symbol A's future
        data contaminates symbol B's past predictions.
        
        Args:
            node: GPNode expression tree to execute
            panel: DataFrame with ticker, date, and feature columns
            feat_cols: List of feature column names to pass to tree execution
            ticker_col: Name of ticker column (default "ticker")
            date_col: Name of date column (default "date")
            
        Returns:
            numpy array of computed values, aligned with panel row order
            
        Example:
            node = parse_formula("ts_mean(close, 20)")
            panel = DataFrame with columns: ticker, date, close, volume, ...
            result = execute_node_grouped(node, panel, ["close", "volume"])
            # result[i] = ts_mean of close for panel.loc[i, "ticker"], 
            # using only that ticker's past 20 bars
        """
        from omega.quant.evolution.genetic_programming import GPIndividual
        
        if ticker_col not in panel.columns or date_col not in panel.columns:
            raise ValueError(
                f"panel must have {ticker_col} and {date_col} columns"
            )
        
        # Store original index to reindex results at the end
        original_index = panel.index.copy()
        work = panel[[ticker_col, date_col] + feat_cols].copy()
        work["_original_idx"] = original_index
        
        results = []
        for ticker, grp in work.groupby(ticker_col, sort=False):
            # Sort by date within this ticker to ensure time-series ops are causal
            grp_sorted = grp.sort_values(date_col).copy()
            
            # Build feature dict for this ticker only
            feat_dict_ticker = {
                col: grp_sorted[col].to_numpy() for col in feat_cols
            }
            
            # Execute tree on this ticker's data
            ind = GPIndividual(tree=node)
            try:
                values = ind._execute_tree(node, feat_dict_ticker)
            except Exception as e:
                logger.warning(
                    f"Tree execution failed for ticker {ticker}: {e}, "
                    f"filling with NaN"
                )
                values = np.full(len(grp_sorted), np.nan)
            
            # Store result with original index for reordering
            results.append(
                pd.DataFrame({
                    "_original_idx": grp_sorted["_original_idx"].values,
                    "value": values,
                })
            )
        
        # Concatenate all ticker results and reindex to original panel order
        result_df = pd.concat(results, ignore_index=True)
        result_df = result_df.set_index("_original_idx").reindex(original_index)
        
        return result_df["value"].to_numpy()

    def _generate_mock_nodes(self, features: Dict[str, np.ndarray]) -> List[GPNode]:
        """
        Generate mock formula nodes for offline/fallback operation.
        
        Returns validated GPNode trees using hardcoded formulas targeted
        for Vietnamese stock market factors.
        """
        # Vietnamese stock market targeted mock formulas
        mock_formulas = [
            "decay_linear(ret_1d, 5)",
            "ts_rank(volume, 20)",
            "div(ts_std(close, 20), ts_mean(volume, 10))"
        ]
        valid_nodes = []
        for formula in mock_formulas:
            try:
                # Apply safety parser
                is_valid, error = self.safety_parser.validate_formula(formula)
                if not is_valid:
                    logger.warning(f"Mock formula rejected by safety parser: {formula} ({error})")
                    continue
                
                node = self.parse_formula(formula)
                if self.validate_expression(node, features):
                    valid_nodes.append(node)
            except Exception as e:
                logger.warning(f"Mock formula parsing failed: {e}")
        return valid_nodes

    def synthesize(
        self, 
        features: Dict[str, np.ndarray],
        top_features: Optional[List[Tuple[str, float]]] = None,
        correlation_clusters: Optional[List[List[str]]] = None,
        prior_failure_stats: Optional[Dict[str, float]] = None,
        bad_motifs: Optional[Set[str]] = None
    ) -> Tuple[List[GPNode], Dict[str, Any]]:
        """
        Synthesize new expressions using configured provider with rejection taxonomy.
        
        Flow:
        1. Generate prompt with optional prior failure context (aggregate only)
        2. Check versioned cache
        3. Call provider if cache miss
        4. Apply safety parser with rejection tracking
        5. Deduplicate normalized formulas
        6. Parse and validate GPNode trees with rejection taxonomy
        7. Cache valid formulas
        8. Return GPNode list + synthesis stats
        
        Args:
            features: Feature dict for validation
            top_features: Optional top features for prompt
            correlation_clusters: Optional clusters for prompt
            prior_failure_stats: Optional aggregate supervised failure metrics
                                (PIT-safe: no row-level labels, only aggregate IC/DSR)
            bad_motifs: Optional set of failed formula patterns to avoid
        
        Returns:
            Tuple of (valid_nodes, synthesis_stats)
            synthesis_stats includes rejection taxonomy and evidence
        """
        # Initialize stats tracking
        stats = {
            "prompt_version": self.prompt_version,
            "max_candidates": self.max_candidates,
            "provider_type": type(self.provider).__name__,
            "cache_hit": False,
            "total_raw": 0,
            "rejection_taxonomy": {
                "parse_error": 0,
                "unsafe_token": 0,
                "duplicate_formula": 0,
                "execution_failure": 0,
                "low_coverage": 0,
                "near_zero_variance": 0,
                "unstable": 0,
                "nan_inf": 0,
            },
            "accepted": 0,
            "rejected_formulas": [],
            "accepted_formulas": [],
        }
        
        # Mock provider always uses fallback
        if isinstance(self.provider, MockProvider):
            nodes = self._generate_mock_nodes(features)
            stats["total_raw"] = len(nodes)
            stats["accepted"] = len(nodes)
            stats["accepted_formulas"] = ["mock_formula_" + str(i) for i in range(len(nodes))]
            return nodes, stats
        
        # Real provider flow with caching and safety
        try:
            # Generate prompt (no secrets, safe to cache)
            if top_features is None:
                top_features = []
            if correlation_clusters is None:
                correlation_clusters = []
            
            prompt = self.generate_prompt(top_features, correlation_clusters, prior_failure_stats, bad_motifs)
            
            # Check versioned cache first
            cached_formulas = self.cache.get(prompt, prompt_version=self.prompt_version)
            if cached_formulas is not None:
                logger.info("Cache hit: using %d cached formulas (version=%s)", 
                           len(cached_formulas), self.prompt_version)
                formulas = cached_formulas
                stats["cache_hit"] = True
            else:
                # Call provider
                logger.info("Cache miss: calling LLM provider to generate formulas")
                formulas = self.provider.generate(prompt)
                
                if not formulas:
                    logger.warning("Provider returned no formulas, falling back to mock")
                    nodes = self._generate_mock_nodes(features)
                    stats["total_raw"] = 0
                    stats["accepted"] = len(nodes)
                    return nodes, stats
                
                stats["total_raw"] = len(formulas)
            
            # Apply safety parser with rejection tracking
            safety_validated = []
            for formula in formulas[:self.max_candidates]:
                is_valid, error = self.safety_parser.validate_formula(formula)
                if is_valid:
                    safety_validated.append(formula)
                else:
                    stats["rejected_formulas"].append({
                        "formula": formula,
                        "reason": error,
                        "stage": "safety_parser"
                    })
                    # Classify rejection reason into taxonomy
                    if "infix" in error.lower() or "syntax" in error.lower():
                        stats["rejection_taxonomy"]["unsafe_token"] += 1
                    elif "unknown" in error.lower():
                        stats["rejection_taxonomy"]["unsafe_token"] += 1
                    elif "lookback" in error.lower():
                        stats["rejection_taxonomy"]["unsafe_token"] += 1
                    elif "depth" in error.lower():
                        stats["rejection_taxonomy"]["unsafe_token"] += 1
                    elif "trailing" in error.lower():
                        stats["rejection_taxonomy"]["unsafe_token"] += 1
                    else:
                        stats["rejection_taxonomy"]["parse_error"] += 1
            
            if not safety_validated:
                logger.warning("All formulas rejected by safety parser, falling back to mock")
                nodes = self._generate_mock_nodes(features)
                stats["accepted"] = len(nodes)
                return nodes, stats
            
            # Deduplicate normalized formulas
            seen_normalized = set()
            unique_formulas = []
            for formula in safety_validated:
                normalized = self.normalize_formula(formula)
                if normalized in seen_normalized:
                    stats["rejection_taxonomy"]["duplicate_formula"] += 1
                    stats["rejected_formulas"].append({
                        "formula": formula,
                        "reason": "Duplicate (normalized)",
                        "stage": "deduplication"
                    })
                    logger.debug("Duplicate formula rejected: %s", formula)
                else:
                    seen_normalized.add(normalized)
                    unique_formulas.append(formula)
            
            # Parse and validate GPNode trees with rejection tracking
            valid_nodes = []
            for formula in unique_formulas:
                try:
                    node = self.parse_formula(formula)
                    if self.validate_expression(node, features):
                        valid_nodes.append(node)
                        stats["accepted_formulas"].append(formula)
                        logger.debug("Formula accepted: %s", formula)
                    else:
                        stats["rejection_taxonomy"]["execution_failure"] += 1
                        stats["rejected_formulas"].append({
                            "formula": formula,
                            "reason": "Execution validation failed",
                            "stage": "validation"
                        })
                        logger.debug("Formula execution validation failed: %s", formula)
                except Exception as e:
                    stats["rejection_taxonomy"]["parse_error"] += 1
                    stats["rejected_formulas"].append({
                        "formula": formula,
                        "reason": f"Parse error: {str(e)}",
                        "stage": "parsing"
                    })
                    logger.warning("Formula parsing failed: %s (%s)", formula, e)
            
            stats["accepted"] = len(valid_nodes)
            
            # Cache unique validated formulas if not from cache
            if not stats["cache_hit"] and unique_formulas:
                self.cache.set(prompt, unique_formulas, prompt_version=self.prompt_version)
                logger.info("Cached %d unique formulas (version=%s)", 
                           len(unique_formulas), self.prompt_version)
            
            if not valid_nodes:
                logger.warning("No valid nodes after parsing, falling back to mock")
                nodes = self._generate_mock_nodes(features)
                stats["accepted"] = len(nodes)
                return nodes, stats
            
            logger.info(
                "Synthesis complete: %d raw, %d safety-validated, %d unique, %d accepted",
                stats["total_raw"],
                len(safety_validated),
                len(unique_formulas),
                len(valid_nodes)
            )
            logger.info(
                "Rejection taxonomy: parse_error=%d unsafe_token=%d duplicate=%d exec_failure=%d",
                stats["rejection_taxonomy"]["parse_error"],
                stats["rejection_taxonomy"]["unsafe_token"],
                stats["rejection_taxonomy"]["duplicate_formula"],
                stats["rejection_taxonomy"]["execution_failure"]
            )
            
            return valid_nodes, stats
            
        except Exception as e:
            logger.error("Synthesis failed: %s, falling back to mock", e)
            nodes = self._generate_mock_nodes(features)
            stats["accepted"] = len(nodes)
            stats["synthesis_error"] = str(e)
            return nodes, stats
    
    def score_and_filter_formulas(
        self,
        nodes: List[GPNode],
        panel: pd.DataFrame,
        feat_cols: List[str],
        labels: Optional[np.ndarray] = None,
        scorer_config: Optional[Any] = None,
        ticker_col: str = "ticker",
        date_col: str = "date",
        synthesis_stats: Optional[Dict[str, Any]] = None,
    ) -> tuple[List[GPNode], Dict[str, Any]]:
        """
        Score and filter formulas using quality metrics with integrated rejection taxonomy.
        
        PIT Safety:
        - Executes formulas on provided panel data (training data only)
        - Labels (if provided) must be from same time period as panel
        - No future/test data is accessed
        
        Args:
            nodes: List of GPNode trees to score
            panel: DataFrame with ticker, date, and feature columns
            feat_cols: List of feature column names
            labels: Optional target labels for supervised scoring (PIT-safe)
            scorer_config: Optional FormulaScorerConfig (uses defaults if None)
            ticker_col: Name of ticker column (default "ticker")
            date_col: Name of date column (default "date")
            synthesis_stats: Optional synthesis stats from synthesize() to merge
        
        Returns:
            Tuple of (accepted_nodes, scoring_stats) where scoring_stats contains
            acceptance/rejection counts, detailed metrics, and rejection taxonomy
        """
        from omega.quant.evolution.llm_formula_scorer import (
            FormulaScorer,
            FormulaScorerConfig,
        )
        
        # Initialize stats, merging synthesis_stats if provided
        base_stats = {
            "total": len(nodes),
            "accepted": 0,
            "rejected": 0,
            "deployable": 0,
            "unsupervised_only": 0,
            "accepted_names": [],
            "rejected_names": [],
            "rejection_reasons": {},
            "details": {},
            "rejection_taxonomy": {
                "parse_error": 0,
                "unsafe_token": 0,
                "duplicate_formula": 0,
                "execution_failure": 0,
                "low_coverage": 0,
                "near_zero_variance": 0,
                "unstable": 0,
                "nan_inf": 0,
            },
        }
        
        # Merge synthesis stats if provided
        if synthesis_stats:
            base_stats["synthesis"] = synthesis_stats
            # Merge rejection taxonomy from synthesis stage
            for key, value in synthesis_stats.get("rejection_taxonomy", {}).items():
                base_stats["rejection_taxonomy"][key] += value
        
        if not nodes:
            logger.warning("score_and_filter_formulas: no nodes to score")
            return [], base_stats
        
        # Initialize scorer with config
        if scorer_config is None:
            scorer_config = FormulaScorerConfig()
        scorer = FormulaScorer(config=scorer_config)
        
        # Execute each formula and collect values
        formula_values = {}
        formula_node_map = {}
        
        for i, node in enumerate(nodes):
            formula_name = f"alpha_llm_{i}"
            try:
                # Execute formula per-ticker (PIT-safe grouped execution)
                values = self.execute_node_grouped(
                    node, panel, feat_cols, ticker_col=ticker_col, date_col=date_col
                )
                formula_values[formula_name] = values
                formula_node_map[formula_name] = node
            except Exception as e:
                base_stats["rejection_taxonomy"]["execution_failure"] += 1
                logger.warning(
                    "Formula execution failed for %s: %s, skipping",
                    formula_name,
                    e,
                )
        
        if not formula_values:
            logger.warning("score_and_filter_formulas: all formulas failed execution")
            base_stats["rejected"] = len(nodes)
            return [], base_stats
        
        # Build ticker group indices for stability check
        ticker_groups = None
        if ticker_col in panel.columns:
            # Encode tickers as integer group IDs
            ticker_map = {t: i for i, t in enumerate(panel[ticker_col].unique())}
            ticker_groups = np.array(
                [ticker_map[t] for t in panel[ticker_col].values],
                dtype=np.int32,
            )
        
        # Score all formulas
        scoring_results = scorer.score_batch(
            formulas=formula_values,
            labels=labels,
            ticker_groups=ticker_groups,
        )
        
        # Filter to accepted formulas and classify rejections into taxonomy
        accepted_nodes = []
        accepted_names = []
        rejected_names = []
        rejection_reasons_by_formula = {}
        deployable_count = 0
        unsupervised_only_count = 0
        
        for formula_name, metrics in scoring_results.items():
            if metrics.accepted:
                accepted_nodes.append(formula_node_map[formula_name])
                accepted_names.append(formula_name)
                if metrics.is_deployable:
                    deployable_count += 1
                if metrics.validation_mode == "unsupervised_only":
                    unsupervised_only_count += 1
            else:
                rejected_names.append(formula_name)
                rejection_reasons_by_formula[formula_name] = metrics.rejection_reasons
                
                # Classify rejection reasons into taxonomy
                for reason in metrics.rejection_reasons:
                    reason_lower = reason.lower()
                    if "coverage" in reason_lower:
                        base_stats["rejection_taxonomy"]["low_coverage"] += 1
                    elif "variance" in reason_lower and "zero" in reason_lower:
                        base_stats["rejection_taxonomy"]["near_zero_variance"] += 1
                    elif "unstable" in reason_lower:
                        base_stats["rejection_taxonomy"]["unstable"] += 1
                    elif "nan" in reason_lower or "inf" in reason_lower:
                        base_stats["rejection_taxonomy"]["nan_inf"] += 1
                    # Note: IC/DSR rejections are supervised validation failures,
                    # not part of the quality taxonomy (they indicate weak signal, not bad data)
        
        # Build summary stats merged with base_stats
        base_stats.update({
            "total": len(nodes),
            "accepted": len(accepted_nodes),
            "rejected": len(rejected_names),
            "deployable": deployable_count,
            "unsupervised_only": unsupervised_only_count,
            "accepted_names": accepted_names,
            "rejected_names": rejected_names,
            "rejection_reasons": rejection_reasons_by_formula,
            "details": {
                name: {
                    "accepted": metrics.accepted,
                    "coverage": metrics.non_nan_coverage,
                    "variance": metrics.variance,
                    "stability": metrics.per_ticker_stability,
                    "nan_inf_ratio": metrics.nan_inf_ratio,
                    "ic": metrics.absolute_ic,
                    "dsr_proxy": metrics.dsr_proxy,
                    "is_supervised_validated": metrics.is_supervised_validated,
                    "is_deployable": metrics.is_deployable,
                    "validation_mode": metrics.validation_mode,
                }
                for name, metrics in scoring_results.items()
            },
        })
        
        stats = base_stats
        
        logger.info(
            "Formula scoring complete: %d total, %d accepted (%d deployable, %d unsupervised_only), %d rejected",
            stats["total"],
            stats["accepted"],
            stats["deployable"],
            stats["unsupervised_only"],
            stats["rejected"],
        )
        
        # L3 audit requirement: explicit warning for unsupervised-only formulas
        if stats["unsupervised_only"] > 0:
            logger.warning(
                "Accepted %d UNSUPERVISED-ONLY formulas - "
                "NOT PRODUCTION-DEPLOYABLE without supervised validation. "
                "These formulas passed basic quality checks (coverage, variance, stability) "
                "but have NOT been validated against forward returns.",
                stats["unsupervised_only"],
            )
        
        if rejected_names:
            logger.info("Rejected formulas: %s", ", ".join(rejected_names))
        
        return accepted_nodes, stats
