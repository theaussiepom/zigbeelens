# HACS embedded view — optional HTTPS dashboard address

## Lens family — embedded view decision tree

Shared across [ZigbeeLens](https://github.com/theaussiepom/zigbeelens) and [ThreadLens](https://github.com/theaussiepom/threadlens). See [lens-family.md](lens-family.md).

```text
1. Native companion panel first
      → status, incidents, summary counts, repairs/diagnostics

2. Optional embedded Core dashboard when safe
      → same HTTP/HTTPS scheme as Home Assistant; CSP/frame-ancestors allow embed

3. If embedding blocked or mixed-content unsafe
      → keep native panel + Open Full Dashboard button (new tab)

4. Keep HA menu/burger behaviour usable
      → iframe must not trap navigation; user can always return to HA chrome

5. No mutation/control buttons in companion panel
      → read-only observability only
```

Product-specific URLs and Traefik examples follow below.

---

The embedded dashboard view is **optional**. Most users do not need it. The default HACS experience is the native companion panel plus the **Open Full Dashboard** button.

Embedded view is useful if you want the full ZigbeeLens dashboard to appear inside the Home Assistant sidebar. For browser security reasons, this usually requires Home Assistant and ZigbeeLens Core to **both be served over HTTPS**.

**HTTP is fine** for the native Home Assistant panel and the **Open Full Dashboard** button. You do not need a reverse proxy for normal HACS use.

An HTTPS Core URL may be **required** for the optional embedded dashboard view, but **HTTPS is not authentication**. If the HTTPS route is reachable by users or networks you do not trust, access-control decisions remain your responsibility.

---

## Quick summary

| Home Assistant | ZigbeeLens Core | Embedded view |
|----------------|-----------------|---------------|
| HTTPS | HTTP | Blocked (expected) |
| HTTPS | HTTPS | Works when headers allow embedding |
| HTTP | HTTP | Works |

### Correct Core URLs (Beast example)

| Use | URL |
|-----|-----|
| Default HACS / LAN | `http://192.168.100.5:8377` |
| Optional HTTPS / iframe | `https://zigbeelens.theaussiepom.me` |
| **Wrong** | `https://zigbeelens.theaussiepom.me:8377` |

Traefik serves HTTPS on **port 443 only**. Appending `:8377` to an HTTPS hostname hits the wrong port (direct container HTTP), not the reverse proxy.

If Home Assistant uses HTTPS and Core uses `http://192.168.100.5:8377`, the panel shows a friendly blocked explanation — not a broken iframe. **Open Full Dashboard** still works in a new tab.

## When to use HTTPS in front of Core

Use an HTTPS dashboard address only if you **want** embedded view inside the HACS sidebar and accept the extra setup.

You do **not** need HTTPS or a reverse proxy for:

- Native companion panel (status, incidents, networks)
- HACS sensors, repairs, diagnostics
- **Open Full Dashboard** in a new tab

Alternatives to reverse proxy for embedded full UI:

- **HAOS add-on + Ingress** — designed embedded path (same-origin through Home Assistant)
- **Open Full Dashboard** — no proxy

## Overview

```text
Home Assistant (HTTPS)
  └── HACS companion panel
        └── Try Embedded View
              └── https://zigbeelens.yourname.example  (HTTPS Core URL)
                        └── reverse proxy (TLS)
                              └── http://zigbeelens:8377  (Core container)
```

After setup:

1. Core is reachable at an **HTTPS** URL from the browser running Home Assistant.
2. **Settings → Devices & services → ZigbeeLens → Configure** — set Core URL to that HTTPS address.
3. **Try Embedded View** renders the dashboard.

Core sends `Content-Security-Policy: frame-ancestors *`. Your reverse proxy must not override this with a stricter policy unless you allow the Home Assistant origin explicitly.

---

## Technical note — mixed content and headers

Browsers block embedding an HTTP dashboard inside an HTTPS Home Assistant page (**mixed content**).

For embedded view through Traefik or another proxy, also check:

- `Content-Security-Policy: frame-ancestors` must allow your Home Assistant origin (not `*` at the proxy unless you intentionally mirror the MASS/Scrypted pattern)
- `X-Frame-Options: DENY` blocks embedding
- SSE may need proxy buffering disabled (`flush_interval -1` on Caddy, or equivalent)

---

## Option A — Beast / Traefik (existing homelab reverse proxy)

For Beast-style Traefik stacks, see:

- `deploy/docker/docker-compose.beast-traefik.example.yaml` — Docker labels for UI (Authentik)
- `deploy/traefik/zigbeelens-router.yaml.example` — file provider router for `/api` (no Authentik)
- `deploy/traefik/security-headers-zigbeelens.yaml.example` — CSP + iframe headers

These follow existing conventions (`local@file`, `authentik@file`, `securityHeadersZigbeeLens@file`, Cloudflare cert resolver, `underground` network). Create a matching Authentik provider for `zigbeelens.${DOMAIN}` before enabling the UI route.

**API bypass (required for HACS over HTTPS):** Home Assistant config flow calls `GET /api/health` (legacy; `GET /api/v1/health` is equivalent). If Authentik protects all paths, those requests get `302` and setup fails. Mirror the ThreadLens split:

- **`zigbeelens-api`** — `PathPrefix(/api)`, priority 100, `local@file` + security headers, **no Authentik**
- **`zigbeelens`** — UI/dashboard, Authentik on Docker labels or a second file router

Example HTTPS Core URL: `https://zigbeelens.theaussiepom.me` (no port suffix).

---

## Option B — Caddy (self-contained example, good for LAN)

Included in the repo: `deploy/docker/docker-compose.caddy.example.yaml` + `deploy/docker/Caddyfile.example`.

### 1. Prepare config

```bash
mkdir -p ~/zigbeelens-https/{config,data}
cp deploy/docker/config.example.yaml ~/zigbeelens-https/config/config.yaml
cp deploy/docker/Caddyfile.example ~/zigbeelens-https/Caddyfile
cp deploy/docker/docker-compose.caddy.example.yaml ~/zigbeelens-https/docker-compose.yaml
```

Edit `Caddyfile` — set a hostname that resolves to your Docker host, for example `zigbeelens.home.arpa`.

Add DNS or `/etc/hosts` on **every device** that opens Home Assistant (including the HA host if it runs a browser):

```text
192.168.100.5  zigbeelens.home.arpa
```

Replace `192.168.100.5` with your Beast (or Docker host) LAN IP.

### 2. Start stack

```bash
cd ~/zigbeelens-https
docker compose up -d
```

Core is **not** published on `:8377` in this example — only Caddy on `:8443` (mapped to container 443).

Verify:

```bash
curl -k https://zigbeelens.home.arpa:8443/api/health
```

### 3. Trust Caddy's internal certificate

The example uses `tls internal` (Caddy local CA). Browsers must trust that CA or the iframe will fail for certificate reasons even after mixed content is fixed.

On the Docker host (installs into system trust store — adjust for your OS):

```bash
docker compose exec caddy caddy trust
```

On other machines, export and install the root CA, or use a publicly trusted certificate (Let's Encrypt) instead — see below.

Home Assistant must also reach `https://zigbeelens.home.arpa:8443/api/health` (integration backend), not only your browser.

### 4. Update HACS integration

**Settings → Devices & services → ZigbeeLens → Configure**

| Field | Value |
|-------|--------|
| Core URL | `https://zigbeelens.home.arpa:8443` |
| Verify SSL | On if cert is trusted; off only for testing with self-signed |

Restart Home Assistant if prompted.

### 5. Test embedded view

1. Sidebar → **ZigbeeLens**
2. **Try Embedded View** → full dashboard should load in the panel
3. **Back to Summary** → returns to companion panel

If you still see blocked or certificate errors, see [Troubleshooting](#troubleshooting) below.

---

## Option B — Traefik (existing external proxy)

If you already run Traefik with TLS:

1. Use `deploy/docker/docker-compose.traefik.example.yaml` as a template.
2. Point DNS at your host (`zigbeelens.example.com`).
3. Ensure the Traefik service disables response buffering if live SSE updates stall.
4. Set HACS Core URL to `https://zigbeelens.example.com` (no port if 443).

See [docker.md](docker.md#reverse-proxy--traefik) for SSE notes.

---

## Option C — nginx (manual)

Minimal location block (adjust hostname, cert paths, and upstream):

```nginx
server {
    listen 443 ssl http2;
    server_name zigbeelens.home.arpa;

    ssl_certificate     /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8377;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # Required for Server-Sent Events (live dashboard)
        proxy_buffering off;
        proxy_cache off;
    }
}
```

Set HACS Core URL to `https://zigbeelens.home.arpa`.

---

## Let's Encrypt (public hostname)

For a domain with public DNS:

1. Use Caddy with `tls you@example.com` instead of `tls internal`, **or** Traefik with ACME.
2. Map `443:443` on the host.
3. HACS Core URL: `https://zigbeelens.example.com` (no port).

**Security:** ZigbeeLens Core has **no built-in authentication** in v0.1.0. HTTPS adds TLS, not authentication. If Core is reachable beyond users or networks you trust, consider firewall rules, network isolation, VPN, or authentication at the proxy (Authelia, OAuth2 proxy, Authentik, etc.).

---

## Security reminders

- Reverse proxy adds **TLS**, not **authentication**
- If you expose Core beyond users or networks you trust, access-control decisions are your responsibility
- Consider firewall rules, Home Assistant Ingress, network isolation, or an authenticated reverse proxy for broader access
- The MQTT collector remains subscribe-only; the proxy only affects HTTP access to the dashboard/API
- Reports are still redacted before download; do not disable redaction because TLS is enabled

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| "Embedded view is blocked by browser security" | Core URL still `http://` in integration | Set Core URL to `https://...` |
| Blank iframe, certificate error in browser devtools | Untrusted self-signed / internal CA | Trust Caddy CA or use Let's Encrypt |
| Panel works, iframe blank, `NET::ERR_CERT_AUTHORITY_INVALID` | HA device doesn't trust cert | Install CA on that device |
| Integration "cannot connect" after switching to HTTPS | HA backend can't reach HTTPS URL; or Authentik blocking `/api` | Fix DNS/firewall; add API bypass router (see Option A); test `curl -sk https://host/api/health` returns JSON |
| Used `https://host:8377` | Wrong URL — Traefik is on 443, `:8377` is direct HTTP | Use `http://host:8377` or `https://host` (no port) |
| Dashboard loads but "Reconnecting" / stale live data | Proxy buffering SSE | `flush_interval -1` (Caddy) or `proxy_buffering off` (nginx) |
| Open Full Dashboard works, embed doesn't | Mixed content or cert | Check Core URL scheme is `https://` in integration options |

**Open Full Dashboard** should continue to work even when embedded view fails — use it as the fallback.

---

## Related

- [Lens family conventions](lens-family.md)
- [HACS integration](hacs.md)
- [Docker deployment](docker.md)
- [Security](security.md)
- [Troubleshooting](troubleshooting.md)
