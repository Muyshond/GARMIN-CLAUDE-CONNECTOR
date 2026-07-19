#!/usr/bin/env python3
"""One-time interactive Garmin login.

Run this once, interactively, with the same token volume mounted as the
long-running server:

    docker compose run --rm -it garmin-mcp python scripts/garmin_login.py

It prompts for your Garmin email/password and, if your account has MFA
enabled, an MFA code. It then writes OAuth tokens to
GARMIN_TOKENSTORE_PATH (default /data) so the long-running server can
authenticate from the cached tokens alone, without ever seeing your
password. Garmin tokens auto-refresh for months; re-run this script only
if the server starts reporting authentication failures.
"""

import getpass
import os
import sys

from garminconnect import Garmin, GarminConnectAuthenticationError

TOKENSTORE_PATH = os.environ.get("GARMIN_TOKENSTORE_PATH", "/data")


def main() -> int:
    email = os.environ.get("GARMIN_EMAIL") or input("Garmin email: ").strip()
    password = os.environ.get("GARMIN_PASSWORD") or getpass.getpass("Garmin password: ")

    client = Garmin(email, password, prompt_mfa=lambda: input("MFA code: ").strip())
    try:
        client.login(TOKENSTORE_PATH)
    except GarminConnectAuthenticationError as exc:
        print(f"Login failed: {exc}", file=sys.stderr)
        return 1

    print(f"Login succeeded. Tokens cached at {TOKENSTORE_PATH!r}.")
    print("You can now start the long-running server (docker compose up -d).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
