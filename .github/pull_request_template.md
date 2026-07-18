## Summary

Describe the change and the problem it solves.

## Scope

- [ ] Installation
- [ ] Runtime
- [ ] Models
- [ ] Documentation
- [ ] Security
- [ ] Operations

## Validation

Provide the commands and results used to validate this change.

~~~text
./scripts/docs-audit.sh
./scripts/release-audit.sh
~~~

## Checklist

- [ ] No secrets, model binaries or runtime data are included.
- [ ] Documentation is updated.
- [ ] Compose paths remain repository-relative.
- [ ] Model/image locks are updated when necessary.
- [ ] Release audit reports zero errors and zero warnings.
