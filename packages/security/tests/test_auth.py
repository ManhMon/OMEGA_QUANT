"""
Tests for OAuthAuthenticator (auth.py)

Coverage:
    - HS256 token validation (happy path)
    - RS256 token validation via mocked JWKS
    - Expired token rejection
    - Invalid signature rejection
    - Audience/issuer enforcement
    - RBAC role mapping (all AccessLevel values + unknown role fallback)
    - JWKS fetch and cache behaviour
    - AuditTrail integration
    - Constructor validation errors
    - fetch_jwks error paths

Author: Backend Engineer (Role 9)
Date: 2026-05-23
"""

from __future__ import annotations

import time
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import jwt
import pytest
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from omega.security.auth import OAuthAuthenticator, OAuthError
from omega.security.core import AccessLevel, AuditTrail


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SECRET = "test-secret-key-omega-quant"
AUDIENCE = "omega-quant"
ISSUER = "https://idp.example.com"


def _make_hs256_token(
    payload: Dict[str, Any],
    secret: str = SECRET,
    algorithm: str = "HS256",
) -> str:
    return jwt.encode(payload, secret, algorithm=algorithm)


def _base_payload(
    role: str = "developer",
    exp_offset: int = 3600,
    aud: str = AUDIENCE,
    iss: str = ISSUER,
) -> Dict[str, Any]:
    now = int(time.time())
    return {
        "sub": "user-123",
        "role": role,
        "aud": aud,
        "iss": iss,
        "iat": now,
        "exp": now + exp_offset,
    }


@pytest.fixture()
def hs256_auth() -> OAuthAuthenticator:
    return OAuthAuthenticator(
        secret=SECRET,
        audience=AUDIENCE,
        issuer=ISSUER,
    )


@pytest.fixture()
def rsa_keypair():
    """Generate a fresh RSA key pair for RS256 tests."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture()
def rs256_auth(rsa_keypair) -> tuple[OAuthAuthenticator, Any, Any]:
    """Return (authenticator, private_key, public_key) with pre-loaded cache."""
    private_key, public_key = rsa_keypair
    auth = OAuthAuthenticator(
        jwks_uri="https://idp.example.com/.well-known/jwks.json",
        audience=AUDIENCE,
        issuer=ISSUER,
    )
    # Pre-populate cache so tests don't need a live HTTP call
    auth._jwks_cache["__default__"] = public_key
    return auth, private_key, public_key


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------

class TestConstructor:
    def test_raises_if_neither_secret_nor_jwks(self):
        with pytest.raises(ValueError, match="Provide either"):
            OAuthAuthenticator()

    def test_raises_if_both_secret_and_jwks(self):
        with pytest.raises(ValueError, match="not both"):
            OAuthAuthenticator(
                secret=SECRET,
                jwks_uri="https://idp.example.com/.well-known/jwks.json",
            )

    def test_hs256_mode_created(self):
        auth = OAuthAuthenticator(secret=SECRET)
        assert auth.secret == SECRET
        assert auth.jwks_uri is None

    def test_rs256_mode_created(self):
        auth = OAuthAuthenticator(jwks_uri="https://example.com/jwks")
        assert auth.jwks_uri == "https://example.com/jwks"
        assert auth.secret is None


# ---------------------------------------------------------------------------
# HS256 validation
# ---------------------------------------------------------------------------

class TestHS256Validation:
    def test_valid_token_returns_claims(self, hs256_auth):
        token = _make_hs256_token(_base_payload())
        claims = hs256_auth.validate_token(token)
        assert claims["sub"] == "user-123"
        assert claims["role"] == "developer"

    def test_access_level_resolved(self, hs256_auth):
        token = _make_hs256_token(_base_payload(role="admin"))
        claims = hs256_auth.validate_token(token)
        assert claims["access_level"] == AccessLevel.ADMIN

    def test_expired_token_raises(self, hs256_auth):
        token = _make_hs256_token(_base_payload(exp_offset=-1))
        with pytest.raises(OAuthError, match="expired"):
            hs256_auth.validate_token(token)

    def test_wrong_secret_raises(self, hs256_auth):
        token = _make_hs256_token(_base_payload(), secret="wrong-secret")
        with pytest.raises(OAuthError):
            hs256_auth.validate_token(token)

    def test_wrong_audience_raises(self, hs256_auth):
        token = _make_hs256_token(_base_payload(aud="other-service"))
        with pytest.raises(OAuthError, match="audience"):
            hs256_auth.validate_token(token)

    def test_wrong_issuer_raises(self, hs256_auth):
        token = _make_hs256_token(_base_payload(iss="https://evil.com"))
        with pytest.raises(OAuthError, match="issuer"):
            hs256_auth.validate_token(token)

    def test_malformed_token_raises(self, hs256_auth):
        with pytest.raises(OAuthError):
            hs256_auth.validate_token("not.a.jwt")

    def test_no_audience_check_when_not_configured(self):
        auth = OAuthAuthenticator(secret=SECRET, issuer=ISSUER)
        # Token with different audience should still pass (no aud check)
        payload = _base_payload(aud="anything")
        # PyJWT requires options override when token has aud but decoder has none
        token = jwt.encode(payload, SECRET, algorithm="HS256")
        # Without audience configured, PyJWT will raise if token has aud claim
        # This is expected PyJWT behaviour — document it as a known constraint
        # The authenticator surfaces the underlying error as OAuthError
        # (audience in token but not in decoder = InvalidAudienceError)
        with pytest.raises(OAuthError):
            auth.validate_token(token)

    def test_no_issuer_check_when_not_configured(self):
        auth = OAuthAuthenticator(secret=SECRET, audience=AUDIENCE)
        payload = _base_payload(iss="https://any-issuer.com")
        token = _make_hs256_token(payload)
        claims = auth.validate_token(token)
        assert claims["sub"] == "user-123"


# ---------------------------------------------------------------------------
# RS256 validation
# ---------------------------------------------------------------------------

class TestRS256Validation:
    def _make_rs256_token(self, private_key, payload: Dict[str, Any]) -> str:
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return jwt.encode(payload, pem, algorithm="RS256")

    def test_valid_rs256_token(self, rs256_auth):
        auth, private_key, _ = rs256_auth
        token = self._make_rs256_token(private_key, _base_payload())
        claims = auth.validate_token(token)
        assert claims["sub"] == "user-123"

    def test_wrong_private_key_raises(self, rs256_auth):
        auth, _, _ = rs256_auth
        # Sign with a different key
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = self._make_rs256_token(other_key, _base_payload())
        with pytest.raises(OAuthError):
            auth.validate_token(token)

    def test_expired_rs256_token_raises(self, rs256_auth):
        auth, private_key, _ = rs256_auth
        token = self._make_rs256_token(private_key, _base_payload(exp_offset=-1))
        with pytest.raises(OAuthError, match="expired"):
            auth.validate_token(token)

    def test_unknown_kid_triggers_jwks_fetch(self, rs256_auth):
        """Cache miss for kid should trigger fetch_jwks."""
        auth, private_key, public_key = rs256_auth
        auth._jwks_cache.clear()

        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        token = jwt.encode(_base_payload(), pem, algorithm="RS256", headers={"kid": "key-1"})

        with patch.object(auth, "fetch_jwks") as mock_fetch:
            # Simulate fetch populating cache
            def _populate(*_):
                auth._jwks_cache["key-1"] = public_key
            mock_fetch.side_effect = _populate

            claims = auth.validate_token(token)
            mock_fetch.assert_called_once()
            assert claims["sub"] == "user-123"

    def test_missing_key_after_fetch_raises(self, rs256_auth):
        auth, private_key, _ = rs256_auth
        auth._jwks_cache.clear()

        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        token = jwt.encode(_base_payload(), pem, algorithm="RS256", headers={"kid": "missing-kid"})

        with patch.object(auth, "fetch_jwks"):  # fetch does nothing — cache stays empty
            with pytest.raises(OAuthError, match="No public key"):
                auth.validate_token(token)


# ---------------------------------------------------------------------------
# RBAC role mapping
# ---------------------------------------------------------------------------

class TestRoleMapping:
    @pytest.mark.parametrize("role,expected", [
        ("admin", AccessLevel.ADMIN),
        ("developer", AccessLevel.DEVELOPER),
        ("auditor", AccessLevel.AUDITOR),
        ("viewer", AccessLevel.VIEWER),
    ])
    def test_known_roles(self, hs256_auth, role, expected):
        token = _make_hs256_token(_base_payload(role=role))
        claims = hs256_auth.validate_token(token)
        assert claims["access_level"] == expected

    def test_unknown_role_defaults_to_viewer(self, hs256_auth):
        token = _make_hs256_token(_base_payload(role="superuser"))
        claims = hs256_auth.validate_token(token)
        assert claims["access_level"] == AccessLevel.VIEWER

    def test_missing_role_claim_defaults_to_viewer(self, hs256_auth):
        payload = _base_payload()
        del payload["role"]
        token = _make_hs256_token(payload)
        claims = hs256_auth.validate_token(token)
        assert claims["access_level"] == AccessLevel.VIEWER


# ---------------------------------------------------------------------------
# JWKS fetch
# ---------------------------------------------------------------------------

class TestJWKSFetch:
    def test_fetch_jwks_raises_without_uri(self):
        auth = OAuthAuthenticator(secret=SECRET)
        with pytest.raises(OAuthError, match="jwks_uri not configured"):
            auth.fetch_jwks()

    def test_fetch_jwks_http_error_raises(self):
        auth = OAuthAuthenticator(jwks_uri="https://idp.example.com/jwks")
        with patch("omega.security.auth.requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("connection refused")
            with pytest.raises(OAuthError, match="JWKS fetch failed"):
                auth.fetch_jwks()

    def test_fetch_jwks_non_200_raises(self):
        auth = OAuthAuthenticator(jwks_uri="https://idp.example.com/jwks")
        with patch("omega.security.auth.requests.get") as mock_get:
            resp = MagicMock()
            resp.raise_for_status.side_effect = requests.RequestException("404 Not Found")
            mock_get.return_value = resp
            with pytest.raises(OAuthError, match="JWKS fetch failed"):
                auth.fetch_jwks()

    def test_fetch_jwks_populates_cache(self, rsa_keypair):
        _, public_key = rsa_keypair
        auth = OAuthAuthenticator(jwks_uri="https://idp.example.com/jwks")

        import json
        from jwt.algorithms import RSAAlgorithm

        jwk_dict = json.loads(RSAAlgorithm.to_jwk(public_key))
        jwk_dict["kid"] = "key-abc"

        with patch("omega.security.auth.requests.get") as mock_get:
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            resp.json.return_value = {"keys": [jwk_dict]}
            mock_get.return_value = resp

            keys = auth.fetch_jwks()
            assert len(keys) == 1
            assert "key-abc" in auth._jwks_cache


# ---------------------------------------------------------------------------
# AuditTrail integration
# ---------------------------------------------------------------------------

class TestAuditIntegration:
    def test_successful_auth_logged(self, tmp_path):
        audit = AuditTrail(audit_dir=str(tmp_path / "audit"))
        auth = OAuthAuthenticator(secret=SECRET, audience=AUDIENCE, issuer=ISSUER,
                                  audit_trail=audit)
        token = _make_hs256_token(_base_payload())
        auth.validate_token(token, user_hint="test-user")

        events = audit.get_events(event_type="OAUTH")
        assert len(events) == 1
        assert events[0]["result"] == "GRANTED"
        assert events[0]["user"] == "test-user"

    def test_failed_auth_logged(self, tmp_path):
        audit = AuditTrail(audit_dir=str(tmp_path / "audit"))
        auth = OAuthAuthenticator(secret=SECRET, audience=AUDIENCE, issuer=ISSUER,
                                  audit_trail=audit)
        with pytest.raises(OAuthError):
            auth.validate_token("bad.token.here", user_hint="attacker")

        events = audit.get_events(event_type="OAUTH")
        assert len(events) == 1
        assert events[0]["result"] == "DENIED"

    def test_no_audit_trail_does_not_raise(self, hs256_auth):
        # hs256_auth has no audit_trail — should work silently
        token = _make_hs256_token(_base_payload())
        claims = hs256_auth.validate_token(token)
        assert "access_level" in claims
