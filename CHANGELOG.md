# Changelog

All notable changes will be documented here. This project follows Semantic
Versioning and the structure of Keep a Changelog.

## [Unreleased]

### Added

- Public repository security and contribution files.
- Consistent 80-column Markdown prose style with an offline documentation
  check.
- README lifecycle diagram and task-oriented documentation index with validated
  cross-document links.
- Integrity verification for downloaded Flannel manifests.
- Immutable Ubuntu base-image reference.
- From-scratch `socket_vmnet` daemon and Softnet shim installation guide.

### Changed

- Network configuration now rejects unsupported modes and relative shim or
  socket paths before preflight.
- Shim recovery builds use the pinned Cargo lockfile.

## [0.1.0]

### Added

- Initial Tart, socket_vmnet, kubeadm, Flannel, lifecycle, diagnostics, and
  smoke-test automation for an Apple Silicon lab.
