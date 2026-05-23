"""
OMEGA_QUANT OAuth Integration (Phase 8 - Security & Governance)

Purpose:
    OAuthAuthenticator supporting JWT validation (RS256/HS256) and basic JWKS
    retrieval, integrated with existing RBAC (AccessLevel from core.py).

Contract:
    - Input:  JWT token string, JWKS URI or symmetric secret
    - Output: Validated claims dict with resolved AccessLevel, or raises on failure
    - Security: Signature verified before claims trusted; audience/issuer enforced

Assumptions:
    - JWT `role` claim maps to AccessLevel enum values (admin/developer/auditor/viewer)
    - JWKS endpoint returns standard RFC 7517 JSON key set
    - No token caching — caller responsible for session management
    - Sync only — matches existing codebase style

Reference:
    - Phase 8: Security & Governance (P1 gap: OAuth integration)
    - docs/FUNCTIONALITY_GAP_ANALYSIS_20260523.md §P1 Gap #3

Author: Backend Engineer (Role 9)
Date: 2026-05-23
Version: 1.0.0
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import jwt
import requests
from jwt.algorithms import RSAAlgorithm

from .core import AccessLevel, AuditTrail

logger = logging.getLogger(__name__)

# Default role claim key in JWT payload
_ROLE_CLAIM = "role"


class OAuthError(Exception):
    """Raised when OAuth/JWT validation fails."""


class OAuthAuthenticator:
    """
    JWT authenticator with JWKS support and RBAC integration.

    Supports:
    - RS256 via JWKS URI (public key fetched from identity provider)
    - HS256 via shared secret (for internal/test tokens)

    RBAC integration:
    - JWT `role` claim is mapped to AccessLevel
    - Unknown roles default to AccessLevel.VIEWER

    Usage::

        auth = OAuthAuthenticator(jwks_uri="https://idp.example.com/.well-known/jwks.json",
                                  audience="omega-quant", issuer="https://idp.example.com")
        claims = auth.validate_token(token)
        access_level = claims["access_level"]  # AccessLevel enum
    """

    def __init__(
        self,
        jwks_uri: Optional[str] = None,
        secret: Optional[str] = None,
        audience: Optional[str] = None,
        issuer: Optional[str] = None,
        audit_trail: Optional[AuditTrail] = None,
    ) -> None:
        """
        Args:
            jwks_uri:    JWKS endpoint URL for RS256 key retrieval.
                         Mutually exclusive with `secret`.
            secret:      Shared secret for HS256 validation.
                         Mutually exclusive with `jwks_uri`.
            audience:    Expected `aud` claim. None skips audience check.
            issuer:      Expected `iss` claim. None skips issuer check.
            audit_trail: Optional AuditTrail for logging auth events.

        Raises:
            ValueError: If neither or both of jwks_uri/secret are provided.
        """
        if jwks_uri is None and secret is None:
            raise ValueError("Provide either jwks_uri (RS256) or secret (HS256).")
        if jwks_uri is not None and secret is not None:
            raise ValueError("Provide jwks_uri OR secret, not both.")

        self.jwks_uri = jwks_uri
        self.secret = secret
        self.audience = audience
        self.issuer = issuer
        self.audit = audit_trail

        # Cached JWKS keys: kid -> public key object
        self._jwks_cache: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_token(self, token: str, user_hint: str = "unknown") -> Dict[str, Any]:
        """
        Validate a JWT and return enriched claims.

        Args:
            token:     Raw JWT string (Bearer token without "Bearer " prefix).
            user_hint: Identifier for audit logging (e.g. request IP or username).

        Returns:
            Claims dict with an added `access_level` key (AccessLevel enum).

        Raises:
            OAuthError: On any validation failure (expired, bad sig, wrong aud, etc.)
        """
        try:
            claims = self._decode(token)
        except OAuthError:
            self._audit_event(user_hint, "validate_token", "DENIED")
            raise

        claims["access_level"] = self._resolve_access_level(claims)
        self._audit_event(user_hint, "validate_token", "GRANTED", claims.get("sub"))
        return claims

    def fetch_jwks(self) -> List[Dict[str, Any]]:
        """
        Fetch and return raw JWKS keys from the configured URI.

        Returns:
            List of JWK dicts as returned by the identity provider.

        Raises:
            OAuthError: If jwks_uri is not configured or the request fails.
        """
        if self.jwks_uri is None:
            raise OAuthError("jwks_uri not configured; using HS256 secret mode.")

        try:
            resp = requests.get(self.jwks_uri, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise OAuthError(f"JWKS fetch failed: {exc}") from exc

        data = resp.json()
        keys: List[Dict[str, Any]] = data.get("keys", [])
        # Refresh cache
        self._jwks_cache = {}
        for jwk in keys:
            kid = jwk.get("kid", "__default__")
            self._jwks_cache[kid] = RSAAlgorithm.from_jwk(jwk)

        logger.debug("JWKS refreshed: %d key(s) loaded", len(self._jwks_cache))
        return keys

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _decode(self, token: str) -> Dict[str, Any]:
        """Decode and verify JWT signature + standard claims."""
        decode_kwargs: Dict[str, Any] = {
            "algorithms": ["RS256"] if self.jwks_uri else ["HS256"],
            "options": {"verify_exp": True},
        }
        if self.audience:
            decode_kwargs["audience"] = self.audience
        if self.issuer:
            decode_kwargs["issuer"] = self.issuer

        try:
            if self.secret:
                return jwt.decode(token, self.secret, **decode_kwargs)

            # RS256: resolve public key from kid header
            header = jwt.get_unverified_header(token)
            public_key = self._get_public_key(header.get("kid", "__default__"))
            return jwt.decode(token, public_key, **decode_kwargs)

        except jwt.ExpiredSignatureError as exc:
            raise OAuthError("Token has expired.") from exc
        except jwt.InvalidAudienceError as exc:
            raise OAuthError("Invalid audience.") from exc
        except jwt.InvalidIssuerError as exc:
            raise OAuthError("Invalid issuer.") from exc
        except jwt.DecodeError as exc:
            raise OAuthError(f"Token decode error: {exc}") from exc
        except jwt.PyJWTError as exc:
            raise OAuthError(f"JWT validation failed: {exc}") from exc

    def _get_public_key(self, kid: str) -> Any:
        """
        Return cached public key for kid, fetching JWKS if not cached.

        Raises:
            OAuthError: If key not found after fetch.
        """
        if kid not in self._jwks_cache:
            logger.debug("kid '%s' not in cache — fetching JWKS", kid)
            self.fetch_jwks()

        key = self._jwks_cache.get(kid) or self._jwks_cache.get("__default__")
        if key is None:
            raise OAuthError(f"No public key found for kid='{kid}'.")
        return key

    @staticmethod
    def _resolve_access_level(claims: Dict[str, Any]) -> AccessLevel:
        """
        Map JWT `role` claim to AccessLevel.

        Mapping:
            admin     -> AccessLevel.ADMIN
            developer -> AccessLevel.DEVELOPER
            auditor   -> AccessLevel.AUDITOR
            viewer    -> AccessLevel.VIEWER  (default for unknown roles)
        """
        role = claims.get(_ROLE_CLAIM, "")
        try:
            return AccessLevel(role)
        except ValueError:
            logger.warning("Unknown role claim '%s'; defaulting to VIEWER", role)
            return AccessLevel.VIEWER

    def _audit_event(
        self,
        user: str,
        action: str,
        result: str,
        subject: Optional[str] = None,
    ) -> None:
        """Log to AuditTrail if configured."""
        if self.audit is None:
            return
        self.audit.log_event(
            event_type="OAUTH",
            user=user,
            action=action,
            resource="jwt_token",
            result=result,
            details={"sub": subject} if subject else {},
        )
