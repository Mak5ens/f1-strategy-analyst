"""Who calls the API: the visitor's account, read from a token of the SSO, and whether it may act as an analyst.

The SSO (LabbTech Auth) is the only one that issues tokens: an RS256 JWT, in the `auth_token` cookie it shares
with every app of its domain, or sent as a Bearer header by a server that forwards it. The API checks its signature
against the SSO's public keys (JWKS, fetched once then cached), its issuer, audience and expiry, without calling the
SSO per request.

Two roles: a reader (any visitor, with or without an account) and an analyst, named by account id in
`AUTH_ANALYSTS`. Account ids, not emails: the SSO lets an account sign in before its email is confirmed, so an
email in a token proves nothing.

Without `AUTH_JWKS_URI`, the API runs open, as on a developer's machine: every caller is the local analyst.
"""

import logging
from collections.abc import Callable
from typing import Annotated, Any

import jwt
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

log = logging.getLogger(__name__)

COOKIE = "auth_token"


class AuthSettings(BaseSettings):
    """Read from the environment (or `.env`) with the `AUTH_` prefix."""

    model_config = SettingsConfigDict(env_prefix="AUTH_", env_file=".env", extra="ignore")

    # The SSO's public keys, e.g. http://localhost:3003/.well-known/jwks.json. Empty: the API runs open.
    jwks_uri: str = ""
    jwt_issuer: str = "http://localhost:3003"
    jwt_audience: str = "labbtech"
    # Account ids (the tokens' `sub`) that act as analysts, comma-separated.
    analysts: Annotated[frozenset[str], NoDecode] = frozenset()

    @field_validator("analysts", mode="before")
    @classmethod
    def _split(cls, value: object) -> object:
        return frozenset(part.strip() for part in value.split(",") if part.strip()) if isinstance(value, str) else value


class Viewer(BaseModel):
    """The account behind a request."""

    id: str = Field(description="The SSO's account id, the token's `sub`")
    name: str = Field(description="First and last name, else the email")
    email: str | None = None
    analyst: bool = False


LOCAL = Viewer(id="local", name="analyste", analyst=True)

KeyResolver = Callable[[str], Any]


class Authenticator:
    """Reads the viewer from a token. `keys` gives the key that signed a token; tests replace the JWKS with it."""

    def __init__(self, settings: AuthSettings | None = None, *, keys: KeyResolver | None = None) -> None:
        self.settings = settings or AuthSettings()
        self.open = not self.settings.jwks_uri and keys is None
        if self.open:
            log.warning("AUTH_JWKS_URI is not set: the API is open, every caller is an analyst")
            self._keys: KeyResolver | None = None
        elif keys is not None:
            self._keys = keys
        else:
            client = jwt.PyJWKClient(self.settings.jwks_uri, cache_keys=True, lifespan=3600, timeout=5)
            self._keys = lambda token: client.get_signing_key_from_jwt(token).key

    def viewer(self, token: str | None) -> Viewer | None:
        """The token's account, or None for a visitor without one or with a token that does not verify."""
        if self.open:
            return LOCAL
        if not token or self._keys is None:
            return None
        try:
            claims = jwt.decode(
                token,
                self._keys(token),
                algorithms=["RS256"],
                issuer=self.settings.jwt_issuer,
                audience=self.settings.jwt_audience,
                options={"require": ["exp", "sub"]},
            )
        except jwt.PyJWTError as error:
            log.info("token refused: %s", error)
            return None
        names = " ".join(part for part in (claims.get("given_name"), claims.get("family_name")) if part)
        return Viewer(
            id=claims["sub"],
            name=names or claims.get("email") or claims["sub"],
            email=claims.get("email"),
            analyst=claims["sub"] in self.settings.analysts,
        )
