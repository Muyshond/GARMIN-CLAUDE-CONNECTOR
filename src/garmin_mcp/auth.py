"""Static bearer-token auth for the Garmin MCP server.

This is a deliberately simple, single-user auth scheme: one long random
token, checked in constant time. It is enough for Claude Desktop/Code
(which let you attach a custom header to a remote MCP server) and for
claude.ai's web "Request headers" beta field, if available on your
account. It is not a general-purpose OAuth authorization server.
"""

import hmac

from fastmcp.server.auth import AccessToken, TokenVerifier


class StaticBearerTokenVerifier(TokenVerifier):
    """Accepts exactly one static bearer token, compared in constant time."""

    def __init__(self, token: str, **kwargs):
        super().__init__(**kwargs)
        self._token = token

    async def verify_token(self, token: str) -> AccessToken | None:
        if hmac.compare_digest(token, self._token):
            return AccessToken(token=token, client_id="garmin-mcp-static-client", scopes=[])
        return None
