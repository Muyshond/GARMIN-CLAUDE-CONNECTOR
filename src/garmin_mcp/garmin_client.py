"""Thin wrapper around garminconnect.Garmin with token-cache reuse.

The long-running server never receives a Garmin password: it only ever
loads OAuth tokens written by the one-time `scripts/garmin_login.py` run
into GARMIN_TOKENSTORE_PATH. If that token store is missing or expired
beyond what a refresh can fix, tool calls fail with a clear ToolError
telling the operator to re-run the login script.
"""

from __future__ import annotations

import os

from fastmcp.exceptions import ToolError
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

DEFAULT_TOKENSTORE_PATH = os.environ.get("GARMIN_TOKENSTORE_PATH", "/data")


class GarminClient:
    """Lazily-authenticated Garmin Connect client backed by a cached token store."""

    def __init__(self, tokenstore_path: str = DEFAULT_TOKENSTORE_PATH):
        self._tokenstore_path = tokenstore_path
        self._client: Garmin | None = None

    def _login(self) -> Garmin:
        client = Garmin()
        try:
            client.login(self._tokenstore_path)
        except GarminConnectAuthenticationError as exc:
            raise ToolError(
                "No valid Garmin session found at "
                f"{self._tokenstore_path!r}. Run the one-time garmin_login.py "
                "script (see README) to authenticate."
            ) from exc
        return client

    def _ensure_client(self) -> Garmin:
        if self._client is None:
            self._client = self._login()
        return self._client

    def call(self, method_name: str, *args, **kwargs):
        """Call a method on the underlying Garmin client.

        Retries once with a fresh login if the cached session turns out to
        be expired mid-run, then surfaces any remaining failure as a clean
        ToolError instead of a raw stack trace.
        """
        client = self._ensure_client()
        try:
            return getattr(client, method_name)(*args, **kwargs)
        except GarminConnectAuthenticationError:
            self._client = None
            client = self._ensure_client()
            try:
                return getattr(client, method_name)(*args, **kwargs)
            except GarminConnectAuthenticationError as exc:
                raise ToolError(
                    "Garmin authentication failed even after a fresh login "
                    "attempt. Re-run garmin_login.py to refresh the session."
                ) from exc
        except GarminConnectTooManyRequestsError as exc:
            raise ToolError(
                "Garmin Connect rate-limited this server. Try again shortly."
            ) from exc
        except GarminConnectConnectionError as exc:
            raise ToolError(f"Could not reach Garmin Connect: {exc}") from exc
