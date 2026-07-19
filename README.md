# garmin-mcp-server

A personal MCP (Model Context Protocol) server that exposes your own Garmin
Connect data — activities, sleep, HRV, body battery, stress, training
status/readiness, max metrics, personal records, daily summary/steps — as
tools Claude can call, so you can chat with Claude as a coach grounded in
your real data.

Single-user, self-hosted: one Docker container + one static bearer token.
No OAuth server, no third-party hosting.

## Architecture

```
Claude (Desktop / claude.ai webapp)
        │  HTTPS + Authorization: Bearer <token>
        ▼
Synology NAS reverse proxy (DDNS + Let's Encrypt cert)
        │  HTTP over LAN
        ▼
Ubuntu server: Docker container "garmin-mcp" (port 8321)
        │  garminconnect library (cached OAuth token)
        ▼
Garmin Connect
```

## 1. Before you deploy: check for a port collision

This project defaults to port **8321**. Your Ubuntu server already runs
other services, so check first:

```bash
sudo ss -tlnp | grep ':83'
docker ps --format '{{.Names}}\t{{.Ports}}'
```

If 8321 is taken, change the port in both `docker-compose.yml` (the
`ports:` mapping) and pass a different `PORT` env var — the container
itself always listens on whatever `$PORT` says.

## 2. Configure

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # paste into MCP_BEARER_TOKEN
```

Leave `PUBLIC_BASE_URL` for now if you don't have the hostname yet — it's
optional metadata, not required for the bearer-token check to work.

## 3. Build and do the one-time Garmin login

```bash
docker compose build

# One-time, interactive — do NOT use `docker compose up` for this:
docker compose run --rm -it garmin-mcp python scripts/garmin_login.py
```

You'll be prompted for your Garmin email, password, and (if your account
has MFA) an MFA code. This writes OAuth tokens into the `garmin_tokens`
Docker volume. The long-running server will only ever read those cached
tokens — it never sees your password, and the tokens auto-refresh for
months without needing this step again.

## 4. Start the long-running server

```bash
docker compose up -d
curl http://localhost:8321/health   # {"status": "ok"}
```

## 5. Test locally before exposing anything publicly

Verify the bearer-token check works:

```bash
curl -i -X POST http://localhost:8321/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
# -> 401 Unauthorized (no token)

curl -i -X POST http://localhost:8321/mcp \
  -H "Authorization: Bearer <your MCP_BEARER_TOKEN>" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
# -> 200 OK, MCP handshake response
```

Then validate the tool schemas and a real call with the
[MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector)
pointed at `http://localhost:8321/mcp` with the same bearer token, before
going any further. Try `list_activities` and `get_daily_summary` first —
if those work, Garmin auth and the token cache are wired up correctly.

## 6. Synology reverse proxy + HTTPS

1. **DDNS**: DSM Control Panel → External Access → DDNS → add a hostname
   (`*.synology.me`, or your own domain).
2. **Certificate**: Control Panel → Security → Certificate → Add →
   Let's Encrypt, for that hostname. Assign it specifically to the new
   reverse-proxy rule you'll create next (Synology lets different
   proxy rules use different certs on the same box).
3. **Reverse proxy rule**: Control Panel → Login Portal (renamed
   "Application Portal" on some DSM 7.2+ builds) → Advanced → Reverse
   Proxy → Create:
   - Source: HTTPS, `<your-hostname>`, port 443
   - Destination: HTTP, `<ubuntu-server-lan-ip>`, port 8321
4. **Enable WebSocket/streaming support** on the rule — Streamable HTTP
   needs `Upgrade`/`Connection: upgrade` forwarded. DSM 7 exposes this as
   a checkbox in the rule's custom-header settings.
5. **Raise timeouts to ≥300–360s** in the rule's advanced settings.
   Synology's default (~60s) will kill long tool calls well before
   Claude's own 300s budget is reached.
6. Test from outside your LAN (e.g. mobile data, not Wi-Fi):
   ```bash
   curl -i https://<your-hostname>/health
   ```

Optional hardening: a `ufw` rule on the Ubuntu host restricting inbound
`8321` to only the Synology NAS's LAN IP, so nothing else on your network
can reach the (unencrypted-on-the-LAN-hop) bearer-token endpoint
directly.

## 7. Connect Claude

### Claude Desktop (works on Fedora via an unofficial community package)

Claude Desktop isn't officially packaged for Fedora, but community RPMs
that repackage Anthropic's official Electron app exist, e.g.
[christian-korneck/claude-desktop-rpm](https://github.com/christian-korneck/claude-desktop-rpm)
or [aaddrick/claude-desktop-debian](https://github.com/aaddrick/claude-desktop-debian)'s
dnf repo.

Once installed, add the server to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "garmin": {
      "url": "https://<your-hostname>/mcp",
      "headers": {
        "Authorization": "Bearer <your MCP_BEARER_TOKEN>"
      }
    }
  }
}
```

Restart Claude Desktop, then ask something like "list my last 5 Garmin
activities" to confirm it's working end-to-end.

### claude.ai webapp (try it — not guaranteed)

Settings → Connectors → Add custom connector → paste
`https://<your-hostname>/mcp`. Check whether a **"Request headers"**
section appears (this is a beta feature being rolled out) — if so, enter
`Authorization: Bearer <your MCP_BEARER_TOKEN>` there and you're done.

If only OAuth Client ID/Secret fields appear and there's nowhere to put a
bearer token, the webapp can't be wired up to this particular server
design yet. That's a deliberate stopping point (see the plan this project
was built from) — a follow-up OAuth-proxy layer is the known next step,
but only worth building if you actually need webapp access and Desktop
isn't enough.

## Notes on scope and safety

- Tool results deliberately avoid raw GPS/second-by-second data streams
  (see `get_activity_detail` in `src/garmin_mcp/server.py`) to stay well
  under Claude's ~150,000-character tool-result ceiling.
- The `garmin_tokens` Docker volume holds a live Garmin session — treat it
  like a credential (back it up carefully, don't bind-mount it anywhere
  web-servable), not like disposable cache.
- `garminconnect` is a community library that wraps Garmin's undocumented
  mobile-app API. Garmin occasionally changes internals in ways that break
  it; if tool calls start failing with authentication errors after
  working fine before, check for a newer `garminconnect` release before
  assuming your token expired.
