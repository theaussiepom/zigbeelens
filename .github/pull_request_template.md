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

- [ ] Relevant tests pass locally (`uv run pytest -q`, UI tests, shared build/typecheck, packaging validators)
- [ ] Documentation contracts pass (`./scripts/validate-docs.sh`, `./scripts/validate-contracts.sh`)
- [ ] No Zigbee mutation added (no permit join, remove, reset, bind, unbind, OTA, channel changes)
- [ ] No unsafe MQTT publish/request topics added (collector subscribes only; topology remains restricted to the allowlisted network-map request)
- [ ] Reports and redaction considered (new fields registered in redaction if needed)
- [ ] Documentation updated for user-visible changes
- [ ] Screenshots added if UI changed materially
- [ ] Database migration added if schema changed (idempotent, tested)
- [ ] Add-on / Docker / HACS impact considered

## Safety notes

<!-- If touching MQTT, topology, discovery, or reports — describe guardrails verified. -->

## Test plan

<!-- How did you verify this works? -->
