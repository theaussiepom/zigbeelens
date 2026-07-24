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
| 7C1 — documentation truth | Merged |
| 7C2 — screenshots / visual evidence | Deferred |
| 7D — live Beast validation | Deferred; not satisfied by docs or local CI |

## Add-on publication status

The add-on is deferred and is not part of the current HACS release. Keep its
non-regression checks green, but do not publish, advertise, or count it as a
supported route. Its future publication gates still include:

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

## HACS integration publication boundary

The public HACS satellite is not synchronized with the reviewed monorepo
stage. It still contains a materially older integration and advertises
`0.1.13`, while the candidate stage uses the previously unused version
`0.1.14`. The candidate version identifies the staged tree uniquely, but the
tree mismatch remains a publication blocker. Validate the current branch only
with the locally generated package from `./scripts/package-hacs-repo.sh`.
External synchronization or publication requires a separate explicitly
authorized task.

Reviewed public-satellite state (historical evidence):

- repository: `theaussiepom/zigbeelens-hacs`
- commit: `050d118b3e1406343255594fe64cd569e2420888`
- reviewed: `2026-07-23`

That commit advertises integration version `0.1.13`, `@zigbeelens` ownership,
and no Python requirements. Its README and integration implementation remain
materially different from this stage. The satellite is not assumed to remain at
that commit; re-check its current tree immediately before any publication
decision.

### Staged source provenance

The source-tree integration manifest keeps a stable `main` documentation URL
for direct source browsing. A generated local stage has a different,
fail-closed ownership contract. `./scripts/package-hacs-repo.sh` requires the
monorepo Git checkout, selects the checked-out `HEAD` commit, rejects a supplied
`ZIGBEELENS_SOURCE_COMMIT` unless it resolves to that same commit, and rejects
tracked changes or nonignored untracked files in every package input. It then
reads those inputs from the selected Git tree, so ignored generated caches
cannot enter the stage, records the commit in `SOURCE_COMMIT`, includes it in
the generated README, and pins both staged installation guides to immutable
`blob/<source-commit>/docs/hacs.md` and `docs/docker.md` pages.

`ZIGBEELENS_SOURCE_REPOSITORY` identifies the source repository used by those
immutable links and defaults to `theaussiepom/zigbeelens`.
`ZIGBEELENS_FUTURE_HACS_REPOSITORY` independently identifies the conditional
future publication destination and defaults to
`theaussiepom/zigbeelens-hacs`. Neither setting rewrites the fixed historical
repository, commit, and review date above. The selected tree, provenance file,
README, and manifest must agree. This identifies the reviewed monorepo source;
it does not establish satellite synchronization or publication readiness.

The reviewed monorepo/stage now owns:

- durable 15–900-second options plus one effective reload;
- fail-closed Core version and capabilities states;
- distinct older/newer/malformed Decision contract and exact-v2 payload repairs;
- `single_config_entry: true` plus runtime concurrency/setup ownership;
- exact Home Assistant `2025.1.0` / Python `3.12` and Home Assistant
  `2026.7.3` / Python `3.14` lanes; and
- generated CI jobs for structural/provenance validation, both exact HA lanes,
  pinned official hassfest, and pinned official HACS validation.

Generated `release.yml` calls the generated CI workflow and makes release
publication depend on it. These templates establish ownership, not a remote
pass: the official jobs must still run successfully on the synchronized
satellite tree.

The integration reads Core diagnostic/configuration/Decision/capability and
bounded inventory data. Its sole write is the exact Core-local Home Assistant
enrichment snapshot, with optional exact clear during explicit config-entry
removal. The manager owns initial/event/retry/15-minute reconciliation and
retains the prior accepted snapshot on unavailable or transient failure.

Before restoring public HACS installation guidance or publishing the satellite:

- prove the complete staged tree matches the intended satellite tree;
- assign a manifest/package version that uniquely identifies that exact tree;
- pass the generated exact Home Assistant 2025.1.0/Python 3.12 and
  2026.7.3/Python 3.14 lanes remotely;
- pass generated official HACS and hassfest validation remotely; and
- record explicit publication authorization before modifying the external
  repository.

## Local pre-release test

See [release-test.md](release-test.md) and `./scripts/local-release-test.sh`.
The integration portion uses a manual install from
`dist/zigbeelens-hacs/custom_components/zigbeelens`, not the public satellite.
