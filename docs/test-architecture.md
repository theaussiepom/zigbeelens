# Test architecture (Phase 7B)

Narrow ownership map for Decision, report, and public-contract confidence.
Phase 7B merged in PR #101 from approved branch tip `03c12d4`. Broader
contributor and product documentation was completed and merged in Phase 7C1.
Phase 7C2 screenshot evidence and Phase 7D live Beast validation remain
deferred.

## Layers

| Layer | Owns | Typical location |
|---|---|---|
| Core unit | Pure Decision status/priority/ranking; reason/limitation/check emission; DataCoverage evaluation | `apps/core/tests/test_*decision*`, `test_*coverage*`, `test_*reason*` |
| Core composition | Evidence composition / Device Story fold from stored facts | `apps/core/tests/test_device_story*.py` |
| Core contract / API | Public DTO + `/api` ↔ `/api/v1` parity; OpenAPI structural fields; oracle freshness | `apps/core/tests/contracts/` |
| UI parser | Wire strictness for public DTOs | `apps/ui/src/lib/decisionContract*.ts` |
| UI ViewModel | Code → copy / presentation mapping | `apps/ui/src/viewModels/**` |
| UI component | Accessibility, interaction, stale-work, transport ownership | `apps/ui/src/components/**`, `pages/**` |
| Cross-surface contract | Core DTO ↔ UI ViewModel ↔ ReportDetailV3 semantic parity | `apps/ui/src/test/contracts/*parity*` |
| Performance | Query/cardinality bounds (not prose correctness) | `apps/core/tests/performance/` |
| HACS | Exact companion, enrichment, lifecycle, compatibility, matrix, and package contracts | `apps/ha_integration/tests/` |

Each behaviour should have **one primary owner**. Higher layers may integrate; they must not re-own lower-layer logic.

## Canonical fixture authority

- Generator: `apps/core/scripts/generate_oracle_mock_fixtures.py`
- Checked-in corpus: `apps/ui/src/test/fixtures/oracleMockScenarios.json`
- Shape:

```json
{
  "oracle_contract_version": 2,
  "vocabulary": { "...": ["sorted", "unique", "from Core registries"] },
  "scenarios": {
    "<id>": {
      "dashboard": {},
      "devices": [],
      "networks": [],
      "incidents": [],
      "report": {},
      "device_stories": { "<network>|<ieee>": {} },
      "report_story_keys": { "<network>|<ieee>": "<network>|<redacted_ieee>" },
      "representative_subjects": []
    }
  }
}
```

Rules:

- Fixed mock clock (`NOW`) and redaction salt (`zigbeelens-oracle-fixture-v1`).
- Vocabulary is derived from Core enums/registries, never from scenario emission.
- Deterministic scenario / device order; sorted JSON keys; byte-stable output.
- Current report is always non-null exact ReportDetailV3 (`report_version === 3` int).
- Generation failure exits nonzero and does not overwrite the checked-in file.
- Ordinary UI Vitest must **not** spawn Core/Python.

### Fixture freshness owner

Exactly one Core test performs two complete generations
(`PYTHONHASHSEED=1` and `PYTHONHASHSEED=42`), asserts byte identity, and
compares to the checked-in fixture:

`apps/core/tests/contracts/test_oracle_fixture_freshness.py`

`scripts/validate-contracts.sh` does **not** regenerate before pytest.
Cheap shape/vocabulary tests load the checked-in fixture only.

### When a golden fixture may change

Only when a deliberate public contract change is accepted (new Decision code,
report v3 field, vocabulary registry, or redaction join key).

## Reports: pre-release v3-only reset

There is **no** stored-report v1/v2 compatibility promise.

Migration `014_report_v3_only_reset.sql` (`DELETE FROM reports`) clears all
development-era saved reports once when upgrading schema 13 → 14.

After migration 014:

- only newly generated exact ReportDetailV3 reports exist;
- every stored report read (list, detail, download) validates exact ReportDetailV3;
- public Saved-report summary fields are owned by the validated body (not stale
  row metadata); row/body `id` mismatch fails closed;
- malformed / non-v3 bodies fail closed and are omitted from Saved reports;
- one report parser, one ViewModel path, one current report contract suite;
- `DecisionPriority` is wire/order contract metadata (exact enum + ranking), not
  a user-facing label catalogue; statuses and primary copy codes own presentation.

This is a deliberate pre-release reset, not a user-facing migration feature.

## Contract lanes

```bash
# Fast (not sufficient for merge alone). Self-contained: no uv required.
# Optional: CORE_PYTHON=/path/to/python
scripts/validate-contracts.sh

# Core contracts only
cd apps/core && python -m pytest -q tests/contracts

# UI contracts only (no Python)
pnpm --filter @zigbeelens/ui test:contracts

# Full suites (retain)
cd apps/core && uv run pytest -q
cd apps/core && uv run pytest -q tests/performance
pnpm --filter @zigbeelens/ui test
```

Python resolution in `validate-contracts.sh`:

1. `CORE_PYTHON` when set;
2. `apps/core/.venv/bin/python` when executable;
3. `python3`;
4. `python`;
5. otherwise fail clearly.

## Home Assistant release-readiness lanes

HACS invariants have narrow production-test owners:

| Invariant | Primary owner |
|-----------|---------------|
| Official HA registry extraction, deterministic entity/area choice, and fail-closed IEEE ambiguity | `test_ha_enrichment.py` |
| Exact Core inventory resolution and duplicate-network behavior | `test_ha_enrichment.py` |
| Strict request/response route and allowed-mutation architecture | `test_api_enrichment.py` |
| Initial/event/retry/periodic reconciliation, exact builder/Core count aggregation, partial-acceptance recovery, complete-empty vs unavailable, and cleanup | `test_enrichment_manager.py` |
| Identity-free coverage states, immediate owner-aware repair transitions, reauth precedence, promotion, and unload safety | `test_enrichment_manager.py`, setup/repair/diagnostics tests |
| Core version, capabilities, Decision contract/payload, enrichment contract, repairs, and panel projection states | compatibility/coordinator/repairs/panel tests |
| Durable options and exactly one effective reload | `test_config_flow.py`, setup tests |
| Runtime plus declarative single-entry ownership | manifest/config-flow/setup/package tests |
| Core storage/projection/report/redaction lifecycle plus independent post-commit, prefix-parity SSE/Dashboard attempts and categorical cause coalescing | Core `test_ha_enrichment.py`, `test_bearer_auth.py`, `test_evaluation_pipeline.py`, and report tests |
| Delivery-aware two-event UI enrichment refresh ownership, missed/delayed companion convergence, immediate SSE reconnect reconciliation, accepted/stale presentation, projection rename/area/removal, and raw-resource negative scope | UI `events.test.ts`, `liveResourceEvents.test.ts`, `useLiveResource.test.tsx`, `EnrichmentLiveRefresh.test.tsx`, `AcceptedRefreshSafety.test.tsx`, and topology refresh tests |
| Live official HA registry → manager/client → Core SQLite/SSE/projection → mounted UI rename/area/removal convergence | `scripts/test-enrichment-live-e2e.sh` on exact HA `2025.1.0` / Python `3.12` |

The production convergence chain has an owner at every boundary: HA manager
tests prove the exact snapshot and retry decision, Core route tests prove
commit-before-notification plus independent identity-free event and Dashboard
attempts, and UI live-resource tests dispatch the real enrichment-then-Dashboard
sequence, missing-exact fallback, and reconnect paths while proving exact
resource ownership and retained accepted data.
Integration coverage must exercise rename/area and removal through those
production schemas and hooks; a test-only shortcut may not publish the event,
filter the companion Dashboard event, rewrite the payload, or project display
names independently.

Monorepo PR/main CI and the `v*` release workflow run
`scripts/test-enrichment-live-e2e.sh` as a dedicated required
`enrichment-live-e2e` job. Packaging and the tag release gate depend on that
job. Generated HACS workflows remain package-scoped because their tree contains
neither Core, the UI, nor this cross-runtime harness; their HA matrix and
official validators do not replace the green live-E2E result for the exact
monorepo source commit.

The exact compatibility matrix is checked in at
`apps/ha_integration/ha-test-matrix.json`:

| Lane | Home Assistant | Python |
|------|----------------|--------|
| Minimum | `2025.1.0` | `3.12` |
| Current | `2026.7.3` | `3.14` |

Both requirements files use `homeassistant==...`, and
`scripts/test-ha-integration-matrix.sh` verifies the imported version before
running the same integration suite. Monorepo CI/release-check and generated
HACS CI use those exact pins.

The generated HACS `ci.yml` owns structural/provenance validation, both exact
matrix lanes, the pinned official `home-assistant/actions/hassfest` action, and
the pinned official `hacs/action`. Generated `release.yml` calls that CI
workflow and makes publication depend on it. Structural contract tests verify
that ownership; only execution on the synchronized satellite is remote
publication evidence.

## Intentional xfail

The full Core suite currently has one intentional non-strict xfail:

`test_incident_badge_matches_device_story_for_model_pattern`

It records a pre-existing Decision-surface mismatch (`watch` versus
`informational`) for model-pattern badges. Release evidence must report it as
**xfail**, not pass. Any additional xfail or skip is a new result that requires
review.

The canonical Core suite's SQLite 3.34.1 case is intentionally delegated to
`scripts/smoke-sqlite-3.34.1.sh`. The release UI safety owner resolves the
repository root once and keeps two corpus diagnostics separate. It scans Core
UI production `.ts` and `.tsx` under `apps/ui/src`, excluding declarations plus
test, contract, fixture, and generated paths relative to that source root. It
also scans the canonical Home Assistant companion-panel JavaScript under
`apps/ha_integration/custom_components/zigbeelens/panel` and requires
`zigbeelens-panel.js`. Either missing source or an empty corpus is a failure,
and both corpora use the same Zigbee mutation-control phrase policy.
`scripts/validate-safety-guardrails.sh` remains the single release wrapper and
fails on zero collected tests or any skipped test. Its release output reports
the production file count for each corpus so path or discovery drift is visible.

## Adding a new Decision code

1. Core model / registry.
2. Core decision unit tests.
3. Regenerate oracle fixture (vocabulary updates automatically).
4. Report presenter mapping (if report-visible).
5. UI parser acceptance.
6. UI ViewModel / `decisionCopy` arrays + mappings (must equal manifest).
7. Component/copy tests only where interaction needs it.
8. Run `scripts/validate-contracts.sh` then full Core/UI suites.

## Adding a new public DTO field

1. Core schema + serializer.
2. OpenAPI structural assertion for required fields (resolved `$ref`/`allOf`).
3. `/api` and `/api/v1` parity row if dual-mounted.
4. UI parser + types.
5. Fixture regeneration if oracle surfaces include the DTO.

## Shared test support

- Core: `apps/core/tests/support/`
- UI: `apps/ui/src/test/contracts/`
- Exact topology evidence-graph DTOs: `apps/ui/src/test/topologyEvidenceGraphFixture.ts`

Production modules must not import test support or fixtures.

The topology fixture builder owns the complete `TopologyEvidenceGraphDetail`
shape for component and page tests. Tests may override deliberate evidence,
but must not substitute the smaller `TopologyNetworkDetail` payload or cast an
incomplete object. Its structural counts, exact inverse layout flags, snapshot
link count, history/last-known window coherence, null-snapshot topology-history
emptiness, and device-stat window integer/cap bounds are derived or validated
from the supplied evidence. A null latest snapshot requires empty recent
topology history and a zeroed last-known result, while passive and
availability-derived evidence remain permitted. Defaults mirror Core's
three-snapshot recent-history cap and seven-day, ten-snapshot device-stat
window; malformed-payload tests must use the builder's named
inconsistent-override opt-in. Resource-state tests separately
represent no accepted data, accepted empty data, accepted nonempty data, and
retained accepted data with a refresh error.

Mesh history-control evaluation copy is owned by
`connectionHistoryPresentationViewModel.test.ts`; page tests own the control and
drawer integration. Core's exact limited-layout payload is classified by the
ViewModel, while `TopologyGraphPage` owns its limited-layout presentation and
does not render graph sidebar controls without usable layout evidence.
`useGraphSelection.test.tsx` owns identity resolution across accepted evidence
replacements, while page tests prove open drawers update and close with
production evidence. Investigation focus likewise stores only an id and page
tests prove that current card membership owns graph focus after refresh.
Overview visit-watermark tests own the rule that the first accepted Core
`dashboard.generated_at` is stable within each native/scenario scope, v1 data
is discarded because its scope is ambiguous, and future browser-clock
boundaries are reset conservatively.

## Zero-fallback classifications

`unknownZeroSource.contract.test.ts` owns an exact AST inventory of `?? 0` /
`|| 0` under declared presentation roots. Allowed classifications:

- `factual measured default` — measured empty/zero counts in presentation;
- `safe rendering fallback` — justified rendering defaults only;
- `graph algorithm accumulator` — only exact `Map.get(... ) ?? 0`
  degree/weight/count accumulator expressions in the declared graph modules;
  never a whole-module exemption and never in components/pages/ViewModels.

`meshEvidenceLive.ts` is intentionally mixed: its user-facing Mesh/device copy is
primary-copy owned and statically scanned, while its individually inventoried
`Map.get(... ) ?? 0` expressions remain algorithm-owned accumulators. Primary Mesh
presentation must not be labeled advanced/debug. Absent health or absent
`device_stats` entries remain unknown (`—` / omitted), not fabricated zero.
