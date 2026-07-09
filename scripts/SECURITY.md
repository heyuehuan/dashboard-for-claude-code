# Security notes

## Remote deployment

The dashboard is a static site served by nginx. It contains session metadata (project names,
paths, timestamps, costs) that you may want to protect.

### Cloudflare Access (recommended)

Put the site behind [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/policies/access/).
This is the simplest option — no nginx changes required. Unauthenticated requests are redirected
to a Cloudflare login page before ever reaching your origin.

### Lock origin to Cloudflare IPs (defense-in-depth)

If you use Cloudflare, also restrict nginx to Cloudflare IP ranges so the origin can't be reached
directly (bypassing Access). Add to your nginx server block:

```nginx
# Allow only Cloudflare IPs — update from https://www.cloudflare.com/ips/
# IPv4
allow 173.245.48.0/20;
allow 103.21.244.0/22;
allow 103.22.200.0/22;
allow 103.31.4.0/22;
allow 141.101.64.0/18;
allow 108.162.192.0/18;
allow 190.93.240.0/20;
allow 188.114.96.0/20;
allow 197.234.240.0/22;
allow 198.41.128.0/17;
allow 162.158.0.0/15;
allow 104.16.0.0/13;
allow 104.24.0.0/14;
allow 172.64.0.0/13;
allow 131.0.72.0/22;
# IPv6
allow 2400:cb00::/32;
allow 2606:4700::/32;
allow 2803:f800::/32;
allow 2405:b500::/32;
allow 2405:8100::/32;
allow 2a06:98c0::/29;
allow 2c0f:f248::/32;
deny all;
```

### localhost-only (default)

The server binds to `127.0.0.1` by default, so it is reachable only from your own
machine. To expose it on your LAN (only on networks you trust), set
`DASHBOARD_HOST=0.0.0.0`:

```bash
DASHBOARD_HOST=0.0.0.0 uv run python -m claude_dashboard
```

### Token auth (optional, any deployment)

Set `DASHBOARD_AUTH_TOKEN` to require a bearer token on all API calls. The local SPA will also
require it (pass via `Authorization: Bearer <token>` header or `dashboard_auth` cookie).

```bash
DASHBOARD_AUTH_TOKEN=your-secret-token uv run python -m claude_dashboard
```

### Path redaction (remote export)

Set `DASHBOARD_REDACT_HOME=1` when running `export.py` to replace your home-directory prefix
with `~` in all exported paths, so deployed data contains no absolute personal paths:

```bash
DASHBOARD_REDACT_HOME=1 python scripts/export.py
```
