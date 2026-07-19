"""Single-user GitHub OAuth layer.

Used only as a fallback for Claude clients (Desktop/webapp custom
connector UI) that default to an OAuth handshake and have no field for
a plain bearer token. GitHub is just a convenient, already-trusted
identity provider here — the only thing that matters is that whoever
completes the GitHub login is the one allow-listed account.
"""

from __future__ import annotations

from fastmcp.server.auth.providers.github import GitHubProvider
from fastmcp.server.auth.auth import AccessToken


class SingleUserGitHubProvider(GitHubProvider):
    """GitHubProvider that only grants access to one allow-listed GitHub login."""

    def __init__(self, *, allowed_login: str, **kwargs):
        super().__init__(**kwargs)
        self._allowed_login = allowed_login

    async def verify_token(self, token: str) -> AccessToken | None:
        access_token = await super().verify_token(token)
        if access_token is None:
            return None
        login = (access_token.claims or {}).get("login")
        if login != self._allowed_login:
            return None
        return access_token
