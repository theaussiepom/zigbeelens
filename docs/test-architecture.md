# Test architecture (Phase 7B)

Narrow ownership map for Decision, report, and public-contract confidence.
This is not broad contributor documentation (Phase 7D).

## Layers

| Layer | Owns | Typical location |
|---|---|---|
| Core unit | Pure Decision status/priority/ranking; reason/limitation/check emission; DataCoverage evaluation | `apps/core/tests/test_*decision*`, `test_*coverage*`, `test_*reason*` |
| Core composition | Evidence composition / Device Story fold from stored facts | `apps/core/tests/test_device_story*.py` |
| Core contract / API | Public DTO + `/api` ↔ `/api/v1` parity; OpenAPI structural fields | `apps/core/tests/contracts/` |
| UI parser | Wire strictness for public DTOs | `apps/ui/src/lib/decisionContract*.ts` |
| UI ViewModel | Code → copy / presentation mapping | `apps/ui/src/viewModels/**` |
| UI component | Accessibility, interaction, stale-work, transport ownership | `apps/ui/src/components/**`, `pages/**` |
| Cross-surface contract | Core DTO ↔ UI ViewModel ↔ ReportDetailV3 semantic parity | `apps/ui/src/test/contracts/*parity*` |
| Performance | Query/cardinality bounds (not prose correctness) | `apps/core/tests/performance/` |
| HACS | Exact companion contract | `apps/ha_integration/tests/` |

Each behaviour should have **one primary owner**. Higher layers may integrate; they must not re-own lower-layer logic.

## Canonical fixture authority

- Generator: `apps/core/scripts/generate_oracle_mock_fixtures.py`
- Checked-in corpus: `apps/ui/src/test/fixtures/oracleMockScenarios.json`
- Shape:

```json
{
  "oracle_contract_version": 1,
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
- Deterministic scenario / device order; sorted JSON keys; byte-stable output.
- Current report is always non-null ReportDetailV3 (`report_version == 3`).
- Generation failure exits nonzero and does not overwrite the checked-in file.
- Ordinary UI Vitest must **not** spawn Core/Python.

### When a golden fixture may change

Only when a deliberate public contract change is accepted (new scenario surface,
Decision code emission, report v3 field, or redaction join key). Fixture drift
without a product change is a bug in generation or an unapproved contract change.

### Freshness

- Core: `tests/contracts/test_oracle_fixture_freshness.py`
- CLI: `uv run --directory apps/core python scripts/generate_oracle_mock_fixtures.py --check`
- Fast lane: `scripts/validate-contracts.sh` (runs check twice under distinct `PYTHONHASHSEED`)

## Contract lanes

```bash
# Fast (not sufficient for merge alone)
scripts/validate-contracts.sh

# Core contracts only
cd apps/core && uv run pytest -q tests/contracts

# UI contracts only (no Python)
pnpm --filter @zigbeelens/ui test:contracts

# Full suites (retain)
cd apps/core && uv run pytest -q
cd apps/core && uv run pytest -q tests/performance
pnpm --filter @zigbeelens/ui test
```

## Current vs legacy reports

| Boundary | Expectation |
|---|---|
| Current generation | Exact report version 3; Decision semantics; redaction; contextual scopes |
| Legacy v1/v2 stored | Immutable opaque historical bodies; readable/downloadable; no rewrite to v3; no current Decision parity |

Do not mix these assertion sets.

## Unknown-data matrix

Unknown/null must not become measured `0`, `0%`, `healthy`, `complete`, or
“no issue” unless zero is a separately measured factual value. Covered in:

- `apps/core/tests/contracts/test_unknown_semantics.py`
- `apps/ui/src/test/contracts/unknownNotZero.contract.test.ts`

## Primary-copy guardrails

Owned by `apps/ui/src/test/contracts/primaryCopyGuardrails.contract.test.ts`.

- Strict forbidden positive claims on headlines / reasons / suggested checks.
- Limitation-aware allowance for documented negative caveats (“does not prove…”).
- Exact file+pattern+reason allowlist only (no broad directory exclusions).
- Deliberately unsafe sample must be rejected by the helper.

## Adding a new Decision code

1. Core model / registry (`HeadlineCode` / `ReasonCode` / limitation / check / coverage).
2. Core decision unit tests.
3. Regenerate oracle fixture (`generate_oracle_mock_fixtures.py`).
4. Report presenter mapping (if report-visible).
5. UI parser acceptance (closed vs forward-compatible — document which).
6. UI ViewModel / `decisionCopy` mapping.
7. Component/copy tests only where interaction/accessibility needs it.
8. Run `scripts/validate-contracts.sh` then full Core/UI suites.

## Adding a new public DTO field

1. Core schema + serializer.
2. OpenAPI structural assertion for required fields (not full-document snapshot).
3. `/api` and `/api/v1` parity row if the route is dual-mounted.
4. UI parser + types.
5. Fixture regeneration if oracle surfaces include the DTO.
6. ViewModel/component only if the field is presented.

## Shared test support

- Core: `apps/core/tests/support/`
- UI: `apps/ui/src/test/contracts/`, existing `src/test/*` helpers

Production modules must not import test support or fixtures (guarded by UI
contract test). Prefer extending existing auth/deferred/React Flow/temp-DB
helpers over new frameworks.

## Naming

- Core contract lane: `apps/core/tests/contracts/test_*.py`
- UI contract lane: `*.contract.test.ts` under `apps/ui/src/test/contracts/`
- Performance remains under `tests/performance/` and is not a contract lane
