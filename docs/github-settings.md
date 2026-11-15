# Recommended GitHub repository settings

[Documentation index](README.md) · [Project README](../README.md)

Apply these settings after creating the public repository, they cannot be
fully expressed by files in the repository.

## Security and analysis

- Enable private vulnerability reporting.
- Enable secret scanning, push protection and do not allow routine bypasses.
- Enable Dependabot alerts and security updates.
- Keep CodeQL enabled and require its check before merging.

## Actions

- Set the default `GITHUB_TOKEN` permission to read-only.
- Do not allow GitHub Actions to create or approve pull requests.
- Allow actions from GitHub and explicitly reviewed publishers only.
- Require actions to be pinned to a full-length commit SHA.

## `main` ruleset

- Require a pull request before merging.
- Require at least one approval when more than one maintainer is available.
- Dismiss stale approvals after new commits.
- Require the Static validation matrix and CodeQL checks.
- Block force pushes and branch deletion.
- Require conversation resolution.
- Prefer squash merges and a linear history.
- Optionally require signed commits after all maintainers configure signing.

## Releases

- Create signed, immutable semantic-version tags.
- Never move a published tag or replace a published release asset.
- Follow [releasing.md](releasing.md) for integrity and live-lab checks.

## Related documentation

- [Release checklist](releasing.md) defines the release procedure.
- [Security policy](../SECURITY.md) defines private vulnerability reporting.
- [Contributing](../CONTRIBUTING.md) defines pull-request expectations.
