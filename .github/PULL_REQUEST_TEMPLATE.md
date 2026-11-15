## Summary

Describe the problem and the proposed change.

## Safety impact

- [ ] This change does not weaken destructive-operation confirmations.
- [ ] This change does not print, persist, or commit credentials or bootstrap
      tokens.
- [ ] Existing initialized clusters remain protected from implicit reset or
      reinitialization.
- [ ] Documentation is updated for user-visible command or configuration
      changes.

## Validation

- [ ] `make validate`
- [ ] `shellcheck scripts/guest/prepare-node.sh scripts/host/*.sh`
- [ ] Relevant macOS/Tart integration behavior was tested or explicitly marked
      untested.
