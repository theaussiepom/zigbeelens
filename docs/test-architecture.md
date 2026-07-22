# Test architecture (Phase 7B)

Narrow ownership map for Decision, report, and public-contract confidence.
This is not broad contributor documentation (Phase 7C).

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
| HACS | Exact companion contract | `apps/ha_integration/tests/` |

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
- malformed / non-v3 bodies fail closed and are omitted from Saved reports;
- one report parser, one ViewModel path, one current report contract suite.
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

Production modules must not import test support or fixtures.
