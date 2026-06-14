## Summary

<!-- What changed and why? -->

## Type of change

- [ ] Bug fix
- [ ] Documentation
- [ ] Release / packaging
- [ ] UI polish
- [ ] Diagnostic rule / report field
- [ ] Other (describe below)

## Checklist

- [ ] Tests pass locally (`pytest apps/core/tests`, `pnpm --filter @zigbeelens/ui test`)
- [ ] No Zigbee mutation added (no permit join, remove, reset, bind, unbind, OTA, channel changes)
- [ ] No unsafe MQTT publish/request topics added (collector remains subscribe-only)
- [ ] Reports and redaction considered (new fields registered in redaction if needed)
- [ ] Documentation updated for user-visible changes
- [ ] Screenshots added if UI changed materially
- [ ] Database migration added if schema changed (idempotent, tested)
- [ ] Add-on / Docker / HACS impact considered

## Safety notes

<!-- If touching MQTT, topology, discovery, or reports — describe guardrails verified. -->

## Test plan

<!-- How did you verify this works? -->
