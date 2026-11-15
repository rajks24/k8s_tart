# Recommended GitHub repository settings

[Documentation index](README.md) · [Project README](../README.md)

Apply these settings after creating the public repository, they cannot be
fully expressed by files in the repository.

## Security and analysis

- Enable private vulnerability reporting.
- Enable secret scanning, push protection and do not allow routine bypasses.

## `main` ruleset

- Require a pull request before merging.
- Require at least one approval when more than one maintainer is available.
- Dismiss stale approvals after new commits.
- Block force pushes and branch deletion.
- Require conversation resolution.
- Prefer squash merges and a linear history.
- Optionally require signed commits after all maintainers configure signing.
- Review the local validation evidence recorded in each pull request.

## Releases

- Create signed, immutable semantic-version tags.
- Never move a published tag or replace a published release asset.
- Follow [releasing.md](releasing.md) for integrity and live-lab checks.

## Related documentation

- [Release checklist](releasing.md) defines the release procedure.
- [Security policy](../SECURITY.md) defines private vulnerability reporting.
- [Contributing](../CONTRIBUTING.md) defines pull-request expectations.
