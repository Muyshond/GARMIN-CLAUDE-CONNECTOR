"""Personal Garmin Connect MCP server.

Exposes a broad set of read-only Garmin Connect tools (activities, sleep,
HRV, body battery, stress, training status/readiness, max metrics,
personal records, daily summary, steps) over Streamable HTTP, protected
by a single static bearer token (see auth.py).

Run directly for local testing:
    MCP_BEARER_TOKEN=... python -m garmin_mcp.server

Run in production via the `app` ASGI object with uvicorn (see Dockerfile):
    uvicorn garmin_mcp.server:app --host 0.0.0.0 --port 8321
"""

from __future__ import annotations

import os

from fastmcp import FastMCP
from fastmcp.server.auth import MultiAuth
from starlette.requests import Request
from starlette.responses import JSONResponse

from garmin_mcp.auth import StaticBearerTokenVerifier
from garmin_mcp.garmin_client import GarminClient
from garmin_mcp.github_auth import SingleUserGitHubProvider

MCP_BEARER_TOKEN = os.environ["MCP_BEARER_TOKEN"]
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL") or None
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET")
ALLOWED_GITHUB_LOGIN = os.environ.get("ALLOWED_GITHUB_LOGIN")

static_verifier = StaticBearerTokenVerifier(token=MCP_BEARER_TOKEN, base_url=PUBLIC_BASE_URL)

if GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET and ALLOWED_GITHUB_LOGIN:
    if not PUBLIC_BASE_URL:
        raise RuntimeError(
            "PUBLIC_BASE_URL must be set when GITHUB_CLIENT_ID/SECRET are configured "
            "(GitHub OAuth needs the real public HTTPS URL to build redirect/metadata URLs)."
        )
    github_provider = SingleUserGitHubProvider(
        client_id=GITHUB_CLIENT_ID,
        client_secret=GITHUB_CLIENT_SECRET,
        base_url=PUBLIC_BASE_URL,
        allowed_login=ALLOWED_GITHUB_LOGIN,
    )
    # Claude Desktop/webapp's custom-connector UI drives the GitHub OAuth
    # flow via DCR; curl/MCP Inspector/claude mcp add can still use the
    # plain static bearer token. required_scopes=[] avoids MultiAuth
    # inheriting GitHub's ["user"] scope requirement and enforcing it even
    # on requests authenticated via the static verifier, whose tokens carry
    # no scopes at all — each verifier already validates what it needs
    # internally.
    auth = MultiAuth(server=github_provider, verifiers=[static_verifier], required_scopes=[])
else:
    auth = static_verifier

mcp = FastMCP(
    name="garmin-coach",
    instructions=(
        "Tools for reading the server owner's own Garmin Connect data: "
        "activities (all sports), sleep, HRV, body battery, stress, "
        "training status/readiness, max metrics (VO2max), personal "
        "records, and daily summary/steps. Dates are 'YYYY-MM-DD' "
        "strings. Use these tools to ground any coaching or training "
        "advice in the person's actual recent data instead of assumptions."
    ),
    auth=auth,
)

garmin = GarminClient()


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.tool
def list_activities(
    start: int = 0, limit: int = 20, activity_type: str | None = None
) -> list[dict]:
    """List recent Garmin activities across all sports, most recent first.

    Args:
        start: Offset into the activity list (0 = most recent).
        limit: Max number of activities to return. Keep this modest
            (default 20) since each activity carries many summary fields.
        activity_type: Optional Garmin activity type key to filter by,
            e.g. "cycling" or "running".
    """
    return garmin.call("get_activities", start, limit, activity_type)


@mcp.tool
def get_activity_detail(activity_id: str) -> dict:
    """Get metadata and per-lap splits for one activity.

    Deliberately omits raw GPS/second-by-second data streams to stay
    small; use list_activities to find an activity_id first.

    Args:
        activity_id: The Garmin activity ID.
    """
    activity = garmin.call("get_activity", activity_id)
    splits = garmin.call("get_activity_splits", activity_id)
    return {"activity": activity, "splits": splits}


@mcp.tool
def get_sleep(date: str) -> dict:
    """Get sleep data for the night ending on the given date.

    Args:
        date: 'YYYY-MM-DD'.
    """
    return garmin.call("get_sleep_data", date)


@mcp.tool
def get_hrv(date: str) -> dict | None:
    """Get heart rate variability (HRV) data for one date.

    Args:
        date: 'YYYY-MM-DD'.
    """
    return garmin.call("get_hrv_data", date)


@mcp.tool
def get_body_battery(start_date: str, end_date: str | None = None) -> list[dict]:
    """Get Body Battery (energy reserve) readings over a date range.

    Args:
        start_date: 'YYYY-MM-DD'.
        end_date: 'YYYY-MM-DD'; defaults to start_date if omitted.
    """
    return garmin.call("get_body_battery", start_date, end_date)


@mcp.tool
def get_stress(date: str) -> dict:
    """Get stress-level data for one date.

    Args:
        date: 'YYYY-MM-DD'.
    """
    return garmin.call("get_stress_data", date)


@mcp.tool
def get_training_status(date: str) -> dict:
    """Get Garmin's training status (e.g. productive, peaking, detraining).

    Args:
        date: 'YYYY-MM-DD'.
    """
    return garmin.call("get_training_status", date)


@mcp.tool
def get_training_readiness(date: str) -> list[dict]:
    """Get training readiness score and its contributing factors.

    Args:
        date: 'YYYY-MM-DD'.
    """
    return garmin.call("get_training_readiness", date)


@mcp.tool
def get_max_metrics(date: str) -> dict:
    """Get max metrics (VO2max, fitness age, etc.) as of one date.

    Args:
        date: 'YYYY-MM-DD'.
    """
    return garmin.call("get_max_metrics", date)


@mcp.tool
def get_personal_records() -> dict:
    """Get the account's all-time personal records."""
    return garmin.call("get_personal_record")


@mcp.tool
def get_daily_summary(date: str) -> dict:
    """Get the daily activity/health summary: steps, calories, distance,
    resting heart rate, etc.

    Args:
        date: 'YYYY-MM-DD'.
    """
    return garmin.call("get_user_summary", date)


@mcp.tool
def get_steps(date: str) -> list[dict]:
    """Get intraday step-count entries for one date.

    Args:
        date: 'YYYY-MM-DD'.
    """
    return garmin.call("get_steps_data", date)


app = mcp.http_app(path="/mcp")


if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8321)),
        path="/mcp",
    )
