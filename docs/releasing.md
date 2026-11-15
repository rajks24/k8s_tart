# Release checklist

[Documentation index](README.md) · [Project README](../README.md)

1. Review `CHANGELOG.md` and move applicable entries from **Unreleased** to the
   release version and date.
2. Update `VERSION` and confirm the changelog uses the same release version.
3. Review upstream changes before updating the Ubuntu image digest, Kubernetes
   repository-key digest, or Flannel version/digest.
4. Provision and destroy a disposable three-node lab on Apple Silicon.
5. Run `make validate`, ShellCheck, `k8sctl test`, and a secret scanner.
6. Confirm `git status --short` contains only intentional release changes and
   no `.state`, credentials, logs, reports, cached manifests, MAC addresses, or
   machine-specific configuration.
7. Open a pull request and review the recorded local validation results.
8. Merge through the protected `main` branch, create a signed `vX.Y.Z` tag,
   and publish release notes from the changelog.

Never replace an existing release tag or asset. Publish a new patch release for
corrections so downstream references remain auditable.

## Related documentation

- [Recommended GitHub settings](github-settings.md) defines the repository
  protections expected before a public release.
- [Contributing](../CONTRIBUTING.md) defines local validation.
- [Security policy](../SECURITY.md) defines reporting and support boundaries.
