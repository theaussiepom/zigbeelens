# Canonical release-candidate screenshots

This directory contains the complete Phase 7C2 screenshot set. Every image is
a capture of the real rendered ZigbeeLens release-candidate product, not a
mockup, component story, generated image, or public-satellite build.
`manifest.json` owns the machine-checked provenance, dimensions, hashes, review
results, and documentation destinations for the set.

## Canonical inventory

| ID | File | Product surface and accepted state | Documentation placement |
|----|------|------------------------------------|-------------------------|
| S1 | `overview-dashboard.png` | Core Overview with the Decision summary, investigation priorities, network/device context, recent changes, and explicit evidence limits | `README.md`, beside the product overview |
| S2 | `mesh-investigate.png` | Core Mesh / Investigate with the evidence graph and metrics, investigation controls, and the HA-enriched Kitchen Lamp drawer | `docs/topology.md`, under Current investigation surfaces |
| S3 | `device-detail-history.png` | Core Device Detail with the Decision status, Device Story, data coverage, snapshot history, HA name/area, and preserved Zigbee2MQTT source identity | `docs/topology.md`, under Current investigation surfaces |
| S4 | `incidents-page.png` | Core incident detail with status, affected scope, evidence, counter-evidence, interpretation, and limitations | `docs/troubleshooting.md`, under Incidents not appearing |
| S5 | `reports-page.png` | Core Saved Reports with current exact-v3 scope, format, redaction ownership, evidence counts, and download actions | `docs/reports.md`, near the current report contract |
| S6 | `report-contextual-create.png` | Core contextual device-report flow with a fixed synthetic target, current controls, and a proven nonempty exact-v3 preview | `docs/reports.md`, under Contextual report flow |
| S7 | `hacs-config-flow.png` | Home Assistant ZigbeeLens config flow from the exact local stage, showing a synthetic Core URL, TLS verification, a blank token, and companion-panel ownership | `docs/hacs.md`, under local staged setup |
| S8 | `hacs-companion-panel.png` | Native Home Assistant companion panel with accepted Core/Decision/enrichment compatibility, factual counts, Decision summary, and the full-dashboard action | `docs/hacs.md`, under Companion panel |
| S9 | `hacs-embedded-blocked.png` | Native panel's real HTTPS-HA/HTTP-Core embedded-view block, with the technical limitation, safe fallback, and Back to Summary | `docs/hacs-embedded-view.md`, beside the mixed-content limitation |

The Core images are evidence-oriented: topology and history are observations,
not proof of a current route, parent, cause, or complete history. The Home
Assistant images show the native companion integration; none is an add-on
panel.

## Provenance

The capture runtime was the immutable source commit
`747374adbf07fe07282a28c5902a335b2bdc80c4`, release-candidate version
`0.1.14`, captured on `2026-07-27`. Core source, the production UI build,
shared contracts, and the locally generated Home Assistant integration stage
all came from that commit. The disposable Home Assistant runtime was exactly
`2026.7.3`, and the installed stage's `SOURCE_COMMIT` matched the capture
commit.

The final documentation commit is expected to differ from the capture commit:
Phase 7C2 adds images, documentation, and validation without changing runtime
behavior. The final HACS stage is regenerated from the final documentation
HEAD, while runtime-file equivalence to the capture source is checked
separately. The unsynchronised public HACS satellite was not installed, read as
a capture source, or modified.

## Capture and image standard

The default was a `1440 × 900` CSS-pixel viewport, device scale factor `1`,
browser zoom `100%`, the production/default theme, reduced motion, no browser
chrome, and no developer overlay. Four documented framing exceptions keep
required product content complete and readable:

| ID | Final dimensions | Exception |
|----|------------------|-----------|
| S1 | `1440 × 820` | The default frame is cropped after the complete recent-change card and before the next section, leaving no partial card |
| S2 | `1680 × 1731` | A `1920 × 1400` viewport is captured as one `1920 × 1731` full-page frame; cropping only the 240-pixel left navigation keeps the complete evidence strip, controls, graph boundary, and HA-enriched drawer readable together |
| S3 | `1440 × 1760` | Taller viewport keeps Device Story, data coverage, snapshot history, identity, HA area, and source name in one truthful state |
| S8 | `1440 × 1100` | Taller viewport includes the complete native Integration health card and its actions |

S4–S7 and S9 use the default `1440 × 900`; every asset uses scale factor `1`
and zoom `100%`.

The browser capture interface returned JPEG raster data. Each accepted raster
was decoded and encoded as PNG without resampling, compositing, text
replacement, retouching, or defect-hiding. Forbidden PNG textual/EXIF chunks
were then removed losslessly without changing pixel data. Cropping and
metadata removal are the only permitted post-capture transformations.

The preferred maximum is 500 KB per image and the hard maximum is 750 KB.
Every file over 500 KB needs a specific rationale in `manifest.json`; text may
not be made harder to read to reduce size.

## Synthetic-data and privacy policy

The entire set is classified as synthetic and
`contains_real_device_identifiers` remains false. The controlled fixture uses
the synthetic `home` / `Home` network, Zigbee2MQTT source names
`source-lamp` and `study-source-lamp`, HA names `Kitchen Lamp` and
`Study Lamp`, and HA areas `Kitchen` and `Study`.

A complete IEEE address may appear only when it was proven to be a tracked,
isolated synthetic-fixture identifier. No complete IEEE from a real
Zigbee2MQTT message, active database, Home Assistant registry, production log,
or operator input may appear. Do not blur or paint over an unsafe identifier;
configure safe data before capture and reject the image if provenance is
uncertain.

Images and PNG metadata must contain no credential, token, session value,
registry/entity ID, deployment-identifying hostname or non-loopback IP address,
filesystem path, person/household name, Wi-Fi detail, production MQTT topic, or
real incident/topology data. A loopback Core origin in the isolated companion
panel is capture-local, not deployment identity. The active ZigbeeLens database
must never be opened, copied, migrated, vacuumed, deleted, or used during
capture.

Each final asset is reviewed at full resolution and again at approximately its
GitHub Markdown display width. Review covers sharp text, complete cards and
actions, graph/drawer/dialog layout, loading or stale states, browser chrome,
privacy, evidence wording, unavailable-versus-zero truth, current Decision and
ReportDetailV3 language, and publication boundaries. Both the privacy and
visual review must be recorded as passed in the manifest.

## Reproducing or refreshing the set

Use a clean detached worktree at the capture source and keep every runtime,
database, certificate, browser profile, and log under a newly created temporary
directory:

1. Verify the detached `HEAD` is
   `747374adbf07fe07282a28c5902a335b2bdc80c4`, repository versions are
   `0.1.14`, and the runtime/package input paths are clean. Record source hashes
   before launching anything.
2. Build the shared package and production UI from that worktree. Create a
   temporary Core configuration whose storage path is a new temporary SQLite
   file, points only to an isolated loopback MQTT broker, uses live production
   mode, and serves the production UI build. Disable unrelated active capture
   behavior. Never point the configuration at an existing database or broker.
3. Populate only the controlled synthetic `home` network and two synthetic
   lamp identities through the normal Zigbee2MQTT/MQTT and Core production
   paths. Produce the accepted Device Story/history, incident, and exact-v3
   report states through product behavior. Confirm every API used by S1–S6
   succeeds, loading and `aria-busy` states settle, and the browser console has
   no error or failed fetch.
4. Generate the local integration with
   `./scripts/package-hacs-repo.sh`, validate it with
   `bash dist/zigbeelens-hacs/scripts/validate-hacs-repo.sh`, and prove its
   `SOURCE_COMMIT`, manifest version, and installed files match the capture
   source. Do not install from HACS or the public satellite.
5. Start a clean disposable Home Assistant `2026.7.3` instance with a new
   temporary configuration directory. While Home Assistant is stopped, copy
   the generated `custom_components/zigbeelens` directory into that
   configuration as one clean unit, then perform a full start.
6. In Home Assistant's real config flow, use a safe synthetic documentation
   Core URL for S7, leave the token blank (or safely masked), and show the
   current TLS and companion-panel controls. Use a separate loopback-only Core
   origin for the working disposable entry used by S8/S9. If the native
   Integration health surface displays that origin, it must remain a
   capture-local loopback value rather than deployment identity.
7. Create synthetic Home Assistant device/area registry records that resolve to
   the controlled Core identities. Confirm initial enrichment, then perform one
   official registry rename/area update and wait for the production default
   two-second debounce. Confirm the subsequent enrichment succeeds and Core
   shows the HA names/areas while preserving Zigbee2MQTT source identity.
8. Open the registered native ZigbeeLens panel and verify accepted Core
   compatibility, Decision contract v2, HA enrichment contract v1, factual
   counts, Decision summary, and Open Full Dashboard before capturing S8.
   Home Assistant logs must contain no event-loop thread-safety marker,
   unhandled task exception, or callback exception.
9. Serve the disposable Home Assistant instance through temporary HTTPS while
   the configured Core origin remains HTTP. Invoke the panel's real Try
   Embedded View path, confirm the browser-enforced mixed-content limitation
   and safe fallback, and capture S9 without DOM mutation.
10. Exercise S1–S9 once without saving assets, then repeat the settled states
    for canonical capture using the dimensions above. Keep the pointer away,
    exclude browser chrome, and reject any frame with a toast, tooltip, loading
    state, stale warning, overlap, clipping, or private data.
11. Convert the returned JPEG rasters to PNG without resampling or editing;
    remove forbidden `tEXt`, `zTXt`, `iTXt`, `eXIf`, and `tIME` chunks; then
    update every manifest hash, size, dimension, route/state, review result,
    and documentation destination.
12. Open all nine final PNGs at full and scaled sizes, run the canonical docs
    validator and its screenshot-contract tests, stop Core, MQTT, Home
    Assistant, and browser sessions, and remove only the disposable temporary
    state.

Any runtime visual change, package-surface change, imagery change, or mixed
capture provenance invalidates the set. Recapture and re-review all S1–S9 from
one immutable source; never refresh only a convenient subset.
