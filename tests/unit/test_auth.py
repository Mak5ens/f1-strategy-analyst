from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from core.auth import LOCAL, Authenticator, AuthSettings

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ANALYST = "3f1c-analyst"


def token(sub: str = ANALYST, *, key: Any = KEY, minutes: int = 15, **claims: Any) -> str:
    payload = {
        "sub": sub,
        "email": "ana@example.com",
        "given_name": "Ana",
        "family_name": "Lyste",
        "iss": "http://localhost:3003",
        "aud": "labbtech",
        "exp": datetime.now(UTC) + timedelta(minutes=minutes),
        **claims,
    }
    return jwt.encode(payload, key, algorithm="RS256")


def authenticator(**settings: Any) -> Authenticator:
    """Signed by `KEY`, as the SSO's JWKS would say."""
    config = AuthSettings(_env_file=None, jwks_uri="http://sso/.well-known/jwks.json", analysts=ANALYST, **settings)
    return Authenticator(config, keys=lambda _: KEY.public_key())


def test_an_analyst_is_named_by_account_id() -> None:
    viewer = authenticator().viewer(token())

    assert viewer is not None
    assert (viewer.id, viewer.name, viewer.email, viewer.analyst) == (ANALYST, "Ana Lyste", "ana@example.com", True)


def test_any_other_account_is_a_reader_even_with_an_analysts_email() -> None:
    viewer = authenticator().viewer(token("someone-else", given_name=None, family_name=None))

    assert viewer is not None and not viewer.analyst and viewer.name == "ana@example.com"


@pytest.mark.parametrize(
    "bad",
    [
        token(key=OTHER),
        token(minutes=-1),
        token(iss="http://elsewhere"),
        token(aud="another-app"),
        jwt.encode({"sub": ANALYST, "iss": "http://localhost:3003", "aud": "labbtech"}, KEY, algorithm="RS256"),
        "not-a-token",
        "",
        None,
    ],
    ids=["other key", "expired", "issuer", "audience", "no expiry", "garbage", "empty", "none"],
)
def test_a_token_that_does_not_verify_is_a_visitor_without_account(bad: str | None) -> None:
    assert authenticator().viewer(bad) is None


def test_a_token_signed_with_a_shared_secret_is_refused() -> None:
    forged = jwt.encode(
        {"sub": ANALYST, "iss": "http://localhost:3003", "aud": "labbtech", "exp": 2**32}, "s" * 32, algorithm="HS256"
    )

    assert authenticator().viewer(forged) is None


def test_analysts_are_read_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_ANALYSTS", " a , b,,c ")

    assert AuthSettings(_env_file=None).analysts == {"a", "b", "c"}


def test_without_an_sso_every_caller_is_the_local_analyst() -> None:
    open_api = Authenticator(AuthSettings(_env_file=None))

    assert open_api.open and open_api.viewer(None) == LOCAL and open_api.viewer("anything") == LOCAL
