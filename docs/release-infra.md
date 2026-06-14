# Release infrastructure inventory

GitHub owner: **theaussiepom**

## Current state

| Item | Status |
|------|--------|
| Version | **0.1.0** (not tagged yet; use `:edge` for testing) |
| Main repo | https://github.com/theaussiepom/zigbeelens |
| HACS repo | https://github.com/theaussiepom/zigbeelens-hacs |
| Add-on repo | https://github.com/theaussiepom/zigbeelens-addons |
| GHCR image | `ghcr.io/theaussiepom/zigbeelens` |
| Pre-release tag | **`edge`** (also `main`, `sha-*`) |
| Main CI | Split jobs — green on `main` |
| Docker workflow | Push `edge` on `main`; version/`latest` on `v*` tags |

## Target images

```
ghcr.io/theaussiepom/zigbeelens:edge      # main branch (pre-release testing)
ghcr.io/theaussiepom/zigbeelens:main      # alias
ghcr.io/theaussiepom/zigbeelens:sha-<sha> # traceability
ghcr.io/theaussiepom/zigbeelens:0.1.0     # release tag (when cut)
ghcr.io/theaussiepom/zigbeelens:latest    # release tag only
```

## Local pre-release test

See [release-test.md](release-test.md) and `./scripts/local-release-test.sh`.
