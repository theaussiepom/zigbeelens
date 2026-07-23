# Release infrastructure inventory

GitHub owner: **theaussiepom**

## Current state

| Item | Status |
|------|--------|
| Version source | Package and manifest versions; validate with `./scripts/check-version-alignment.sh` |
| Main repo | https://github.com/theaussiepom/zigbeelens |
| Public HACS satellite | https://github.com/theaussiepom/zigbeelens-hacs — unsynchronized; not current branch-validation evidence |
| Add-on repo | https://github.com/theaussiepom/zigbeelens-addons |
| GHCR image | `ghcr.io/theaussiepom/zigbeelens` |
| Pre-release tag | **`edge`** (also `main`, `sha-*`) |
| Main CI | Split required jobs; verify the exact release commit before tagging |
| Docker workflow | Push `edge` on `main`; version/`latest` on `v*` tags |

## Target images

```
ghcr.io/theaussiepom/zigbeelens:edge      # main branch (pre-release testing)
ghcr.io/theaussiepom/zigbeelens:main      # alias
ghcr.io/theaussiepom/zigbeelens:sha-<sha> # traceability
ghcr.io/theaussiepom/zigbeelens:<version> # versioned release tag
ghcr.io/theaussiepom/zigbeelens:latest    # release tag only
```

## Release-quality phase status

| Phase | Status |
|-------|--------|
| 7A — query/cardinality/runtime baseline | Merged in PR #100 |
| 7B — test architecture / exact-v3 reset | Merged in PR #101 |
| 7C1 — documentation truth | Current documentation phase |
| 7C2 — screenshots / visual evidence | Deferred until after 7C1 |
| 7D — live Beast validation | Deferred; not satisfied by docs or local CI |

## Add-on publication status

The add-on repository is **blocked from publication** even if its structural
validator passes:

- the packaged repository currently uses the standalone GHCR image entrypoint;
  it generates add-on options and Ingress configuration, but does not install
  or export the optional `security.api_token`, and its UID-1000 `/data`
  writability still needs an HAOS smoke test;
- the add-on schema accepts zero for `reporting.max_*`, while Core requires
  values of at least one;
- `reporting.default_profile` is currently ineffective because the request
  model supplies `standard` before the resolver can fall back to configuration;
- the add-on exposes `ports: {}` in a separate namespace, so there is no
  portable HACS-to-add-on Core origin; only the Ingress UI path is documented.

Close these blockers and run the packaged HAOS Ingress, bearer, and
non-Supervisor spoofing smokes before publishing the add-on repository.

## HACS integration release blocker

The public HACS satellite is not synchronized with the reviewed monorepo
stage. It still contains a materially older integration while both trees
advertise version `0.1.13`; this same-version/different-tree collision prevents
the version from identifying an artifact. Validate the current branch only
with the locally generated package from `./scripts/package-hacs-repo.sh`.
External synchronization or publication requires a separate explicitly
authorized task.

The integration's OptionsFlow accepts a 15–900-second polling interval, manually
updates the entry, and then returns an empty options result. Home Assistant
persists that result over the intermediate update, so the custom interval is
not durable and polling returns to the 60-second default. Fix the flow to return
the selected options and add a persistence/reload test before advertising
configurable polling as release-ready.

The compatibility helper also returns `true` for missing or malformed Core
versions. That violates the documented Unknown tri-state and can contribute to
enabling shared decisions without an observed compatible version. Make unknown
versions fail closed and cover the coordinator/panel projection before HACS
publication.

The coordinator currently collapses exact-v2 payload-shape failure and an
unsupported contract into the same boolean. Repairs consequently emits an
unsupported-contract/upgrade-Core message for malformed or missing Dashboard
decision surfaces. Preserve the failure reason and emit truthful repair state
before publication.

Package metadata declares Home Assistant 2025.1.0 as the minimum, but the
current test dependency resolves a newer version. Add exact-minimum plus current
Home Assistant matrix coverage. The config flow also enforces one entry while
the manifest lacks declarative `single_config_entry` metadata. Run official
HACS/hassfest validation for the staged satellite repository in addition to the
local structural validator before publication.

Before restoring public HACS installation guidance or publishing the satellite:

- prove the complete staged tree matches the intended satellite tree;
- assign a manifest/package version that uniquely identifies that exact tree;
- pass exact Home Assistant 2025.1.0 plus current-version coverage;
- pass official HACS and hassfest validation; and
- record explicit publication authorization before modifying the external
  repository.

## Local pre-release test

See [release-test.md](release-test.md) and `./scripts/local-release-test.sh`.
The integration portion uses a manual install from
`dist/zigbeelens-hacs/custom_components/zigbeelens`, not the public satellite.
