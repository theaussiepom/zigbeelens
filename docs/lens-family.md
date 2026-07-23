# Lens family conventions (historical pointer)

ZigbeeLens remains part of the broader Lens family of read-only home-network
observability tools alongside [ThreadLens](https://github.com/theaussiepom/threadlens).

**Canonical shared conventions (ThreadLens):**  
[ThreadLens docs/lens-family.md](https://github.com/theaussiepom/threadlens/blob/main/docs/lens-family.md)

ZigbeeLens’s **active public diagnostic contract** is decision-led (Track 5),
not the retired Lens-bucket presentation fields (`lens_bucket*`, health-derived
Dashboard collections, Lens MQTT entities).

| Topic | Current ZigbeeLens doc |
|-------|------------------------|
| Decision / API contract | [api.md](api.md), [decision-engine.md](decision-engine.md) |
| MQTT summary entities | [mqtt-discovery.md](mqtt-discovery.md) |
| Reports (exact v3 only after migration 014) | [reports.md](reports.md) |
| HACS companion (contract v2) | [hacs.md](hacs.md) |
| Alignment history | [lens-alignment-status.md](lens-alignment-status.md) |
