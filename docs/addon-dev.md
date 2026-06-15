# ZigbeeLens Home Assistant add-on — developer guide

This document covers building, testing, and installing the ZigbeeLens Home Assistant add-on from the monorepo.

## Layout

```
apps/addon/
  repository.yaml          # HA add-on repository metadata
  zigbeelens/
    config.yaml            # Add-on manifest (options, schema, ingress)
    Dockerfile             # Built from monorepo root
    run.sh                 # Reads /data/options.json → config.yaml → starts Core
    README.md              # User-facing add-on docs
    icon.png / logo.png
    translations/en.yaml
```

## Build the add-on image (recommended)

From the **repository root**:

```bash
chmod +x scripts/build-addon.sh scripts/validate-addon.sh scripts/prepare-addon.sh
./scripts/build-addon.sh
```

This runs:

```bash
docker build -f apps/addon/zigbeelens/Dockerfile -t zigbeelens-addon:local .
```

### Run locally (without Home Assistant)

```bash
mkdir -p data/ha-addon/zigbeelens

cat > data/ha-addon/options.json <<'EOF'
{
  "mqtt": {
    "host": "host.docker.internal",
    "port": 1883,
    "username": "",
    "password": "",
    "tls": { "enabled": false, "reject_unauthorized": true }
  },
  "networks": [
    { "id": "home", "name": "Home", "base_topic": "zigbee2mqtt" }
  ],
  "storage": { "retention_days": 7 },
  "diagnostics": {},
  "reporting": { "default_profile": "standard" },
  "features": {
    "mqtt_collector": true,
    "mqtt_discovery": false,
    "bridge_logs": true,
    "device_payload_history": true,
    "manual_network_map": false,
    "automatic_network_map": false
  }
}
EOF

docker run --rm -p 8377:8377 \
  -v "$(pwd)/data/ha-addon:/data" \
  zigbeelens-addon:local
```

Open http://localhost:8377 — Core serves the bundled UI and API from one port.

## Validate packaging

```bash
./scripts/validate-addon.sh
```

Checks required files, ingress port, default secrets, and runs `test_addon_config.py`.

## Supervisor-compatible build context

Home Assistant Supervisor builds with the **add-on directory** as Docker context (not the monorepo root). To publish to a Supervisor repository:

```bash
./scripts/prepare-addon.sh
docker build -t zigbeelens-addon:supervisor apps/addon/zigbeelens/.build
```

Commit or publish the `.build` output as part of your release pipeline, or publish pre-built multi-arch images and reference them from `config.yaml` with an `image:` key.

## Install as a local add-on (HAOS dev)

1. Build the image on your HA machine or push to a registry your HA host can pull.
2. Create a local add-on directory under `/addons/zigbeelens/` (path varies by install) **or** add this git repository as a custom add-on repo pointing at `apps/addon`.
3. Configure MQTT + networks in the add-on UI.
4. Start the add-on and open Ingress.

For rapid UI iteration without rebuilding the image, continue using `./scripts/dev.sh` (Core + Vite separately). For Ingress-specific testing, use the bundled image.

## Config generation

`run.sh` reads `/data/options.json` (written by the Supervisor from add-on options) and generates `/data/zigbeelens/config.yaml` using `zigbeelens.config.addon`.

Test generation locally:

```bash
source apps/core/.venv/bin/activate
PYTHONPATH=apps/core/src python3 - <<'PY'
import json
from pathlib import Path
from zigbeelens.config.addon import options_to_yaml, safe_startup_log_lines

options = json.loads(Path("data/ha-addon/options.json").read_text())
print(options_to_yaml(options))
print("--- logs ---")
for line in safe_startup_log_lines(options):
    print(line)
PY
```

Passwords appear in the generated YAML (required for MQTT) but **never** in startup logs.

## Ingress / relative URLs

The UI uses **relative API paths** (`api/dashboard`, not `/api/dashboard`) so requests stay under the Ingress prefix (`/api/hassio_ingress/<token>/…`).

Vite builds with `base: "./"` so static assets load under Ingress.

React Router detects HA Ingress basename automatically.

SSE connects via relative `api/events/stream`. If EventSource fails (some proxies), `useLiveResource` polls every 30 seconds and the connection dot shows **disconnected**.

## Testing Ingress locally

Simulate an Ingress basename in the browser devtools console before loading routes, or proxy with nginx:

```nginx
location /api/hassio_ingress/test/ {
    proxy_pass http://127.0.0.1:8377/;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;  # helps SSE
}
```

Then open `http://localhost/api/hassio_ingress/test/`.

## MQTT sample messages

With the add-on connected to a broker, publish Zigbee2MQTT-like retained messages on your configured `base_topic` to populate the dashboard. See [mqtt-dev.md](mqtt-dev.md).

## Logs

Inside HA: **Settings → Add-ons → ZigbeeLens → Log**

Local Docker:

```bash
docker logs -f <container>
```

Startup logs list networks, redacted MQTT URI, storage path, and feature flags — never passwords.

## Reports under add-on path

Report downloads use relative URLs (`api/reports/{id}/download`). Copy Markdown from the Reports page as a fallback if the browser download path is blocked by Ingress.

## Architecture support

| Arch | Status |
|------|--------|
| `amd64` | Supported |
| `aarch64` | Supported (Raspberry Pi 4/5, HA Green/Yellow) |
| `armv7` | Listed in manifest; may require dependency verification on older 32-bit boards |

## Publishing checklist

- [ ] `./scripts/validate-addon.sh` passes
- [ ] `./scripts/build-addon.sh` succeeds on amd64 and aarch64
- [ ] `./scripts/prepare-addon.sh` for Supervisor repo if not using pre-built images
- [ ] Update `apps/addon/zigbeelens/config.yaml` version
- [ ] Update `CHANGELOG.md`
- [ ] Tag release and publish repository / container images
