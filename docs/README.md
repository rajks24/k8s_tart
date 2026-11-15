# Documentation index

[Project README](../README.md) · [Security policy](../SECURITY.md) ·
[Contributing](../CONTRIBUTING.md)

Use this index to choose the shortest path for the task you are performing.
The top-level README remains the authoritative command overview.

## New installation

1. Follow [Softnet shim setup](shim-setup.md) to install `socket_vmnet`, build
   the compatibility shim, configure `cluster.toml`, and pass preflight.
2. Return to [fresh cluster provisioning][fresh-provisioning] to create the VMs,
   configure access, and run `k8sctl up`.
3. Use [networking](networking.md) to reserve addresses before repeated VM
   restarts.
4. Run the smoke test described in the
   [project README](../README.md#what-the-smoke-test-covers).

## Existing cluster

1. Follow the [existing-cluster workflow][existing-workflow] to inspect and
   adopt the cluster without rebuilding it.
2. Read the [operations runbook](runbook.md) for status, diagnostics, restart,
   recovery, and deliberate rebuild procedures.
3. Use [networking](networking.md) for IP drift, DHCP reservations, and
   layer-by-layer connectivity checks.

[existing-workflow]: ../README.md#first-use-with-your-currently-working-cluster
[fresh-provisioning]: ../README.md#full-fresh-cluster-provisioning

## Understand the system

- [Architecture and implementation](architecture.md) explains the macOS host,
  Tart VMs, control paths, cluster roles, and idempotence boundaries.
- [Networking](networking.md) explains the Softnet shim, `socket_vmnet`, VM
  subnet, DHCP, Flannel VXLAN, and IP-drift protections.
- [Project milestones](project-plan.md) records completed phases and future
  improvement ideas.

## Maintain and publish

- [Release checklist](releasing.md) covers versioning, integrity review,
  disposable-lab testing, validation, tags, and release notes.
- [Recommended GitHub settings](github-settings.md) covers repository security,
  Actions policy, branch rules, and release protections.
- [Contributing](../CONTRIBUTING.md) defines development validation and safety
  expectations.
- [Security policy](../SECURITY.md) defines private vulnerability reporting and
  the project's security boundaries.

## Quick routing

| Situation | Read |
|---|---|
| `preflight` cannot find the shim or socket | [Softnet shim setup](shim-setup.md#preflight-troubleshooting) |
| A VM address changed | [Networking: If an IP changes](networking.md#if-an-ip-changes) |
| Nodes or Pods are unhealthy | [Operations: Quick triage](runbook.md#quick-triage) |
| You need to rebuild the lab | [Operations: Rebuild from scratch](runbook.md#rebuild-the-lab-from-scratch) |
| You want to understand command safety | [Architecture: Idempotence boundaries](architecture.md#idempotence-boundaries) |
| You plan to publish a release | [Release checklist](releasing.md) |
