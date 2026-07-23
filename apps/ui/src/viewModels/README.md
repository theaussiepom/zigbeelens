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
  coverage/     # reusable evidence-coverage presentation
  devices/      # decision badges and device rows
  incidents/    # incident list and detail presentation
  overview/     # priorities, recent changes, model patterns, coverage
  reports/      # exact-v3 report decision presentation
  topology/     # investigation, Device Story, snapshots, raw-detail presentation
```

Keep ViewModels at the product-surface level. Do not create ViewModels for generic UI atoms such as buttons or badges.

## Conventions

- DTO field names stay snake_case; ViewModel field names use camelCase.
- Reason, limitation and suggested-check copy lives in `decisionCopy.ts`.
- Unknown reason codes fall back safely — they must not crash rendering.
- Status pill tone is deterministic from `decisionStatusTone()`.
- ViewModels present the shared Decision Engine; they do not add diagnosis or
  data collection.

## Current scope

The current UI uses ViewModels across Overview, Mesh / Investigate, Devices,
Incidents, Reports, Device Story, and topology snapshot/detail surfaces.
Backend decision DTO primitives live under `zigbeelens.decisions`; mirrored
frontend DTOs live under `src/types/decisions.ts`.

Unknown API codes must fall back safely in `decisionCopy.ts` — never expose raw internal codes in user-facing copy.
