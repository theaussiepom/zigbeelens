# ViewModels

ViewModels sit between API DTOs and React components.

```text
API DTO  ->  ViewModel builder  ->  component
```

## Ownership

| Layer | Owns |
|---|---|
| **API DTO** (`src/types/decisions.ts`) | Serialised decision data from the backend |
| **ViewModel** (`src/viewModels/`) | Labels, pill tone, section order, row text, collapsed details |
| **Component** | Rendering, layout, accessibility, local expand/collapse UI state |

Components must not independently decide:

- whether something is worth reviewing;
- whether availability tracking is off;
- whether data coverage is sufficient; or
- what diagnostic copy to show.

Map stable backend codes through `decisionCopy.ts` instead.

## Folder layout

```text
src/viewModels/
  README.md
  types.ts
  decisionCopy.ts
  topology/     # topology ViewModel builders (snapshot history, device details)
  devices/      # future device story ViewModel builders
  reports/      # future report ViewModel builders
```

Keep ViewModels at the product-surface level. Do not create ViewModels for generic UI atoms such as buttons or badges.

## Conventions

- DTO field names stay snake_case; ViewModel field names use camelCase.
- Reason, limitation and suggested-check copy lives in `decisionCopy.ts`.
- Unknown reason codes fall back safely — they must not crash rendering.
- Status pill tone is deterministic from `decisionStatusTone()`.
- Major screen migrations belong to later phases; this folder defines the contract only.

## Phase 1 scope

Phase 1 provides:

- backend decision DTO primitives (`zigbeelens.decisions`);
- frontend mirrored DTO types (`src/types/decisions.ts`);
- copy, status and coverage mapping (`decisionCopy.ts`);
- ViewModel ownership conventions (`types.ts`, this README).

Phase 1 does **not** yet provide:

- migration of existing UI sections (e.g. `SnapshotHistorySection`);
- topology-specific ViewModel builders;
- report ViewModel builders;
- new diagnosis logic;
- new data collection.

Unknown API codes must fall back safely in `decisionCopy.ts` — never expose raw internal codes in user-facing copy.
