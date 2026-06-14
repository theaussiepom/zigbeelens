# Home Assistant Brands CDN

HACS still resolves integration icons from `https://brands.home-assistant.io/_/DOMAIN/icon.png`.
Inline `custom_components/zigbeelens/brand/` assets cover **Settings → Devices & services** in HA 2026.3+, but the HACS downloads UI needs a matching entry in [home-assistant/brands](https://github.com/home-assistant/brands) (same as Scrypted and HACS itself).

## Submit or refresh icons

```bash
./scripts/sync-home-assistant-brands.sh
```

That opens a PR adding `custom_integrations/zigbeelens/` with the PNGs from `apps/ha_integration/custom_components/zigbeelens/brand/`.

After merge, allow up to 24 hours for CDN cache refresh.
