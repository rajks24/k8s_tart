# Work backlog / project milestones

[Documentation index](README.md) · [Project README](../README.md)

## Phase 1 — Adopt and baseline

- [ ] Copy project source to `~/myprojects/k8s_tart` alongside existing shim
      source.
- [ ] Review `config/cluster.toml` for real shim binary and daemon socket.
- [ ] Run `preflight` correct only configuration inaccuracies, not the working
      network.
- [ ] Run `access` only if existing key + passwordless sudo are unavailable.
- [ ] Run `adopt` verify three Kubernetes nodes are Ready and the kubeconfig is
      stored in `.state/`.
- [ ] Run `context use` verify the lab appears in normal
      `kubectl config get-contexts` output.
- [ ] Run `diagnose` to capture a baseline report.

Acceptance: `kubectl get nodes` shows cp/w1/w2 Ready and no VM reinitialized.

## Phase 2 — Stable addresses

- [ ] Collect actual VM NIC MACs and current guest IPs.
- [ ] Back up current macOS `/etc/bootptab`.
- [ ] Add MAC-based DHCP reservations for CURRENT addresses, not new ones.
- [ ] Verify after a planned restart that leases remain unchanged.
- [ ] Fill `reserved_ip` for each VM in TOML.

Acceptance: stop/start cycle changes neither CP nor worker IP.

## Phase 3 — Reprovision and smoke test

- [ ] Run live tests and verify cross-node BusyBox ping.
- [ ] Verify CoreDNS lookup and web Service routing.
- [ ] Verify `doctor`, `status`, `monitor` and `diagnose`.
- [ ] Test `up` again on existing lab and observe no reinstall/reset.
- [ ] On a disposable copy, test a destroy/create/bootstrap cycle.

Acceptance: fresh lab reaches 3 Ready nodes, smoke tests pass and teardown safe.

## Phase 4 — Improvement ideas

- [ ] Dedicated least-privilege SSH/sudo bootstrap image, replacing lab-wide
      NOPASSWD.
- [ ] Automated launchd lifecycle if Mac sleep/reboot behaviour is acceptable.
- [ ] Ansible alternative when scaling beyond three guests.
- [ ] Cilium networking option (separate cluster), baseline policy testing.
- [ ] Local metrics-server + optional Prometheus/Grafana + resource alerts.
- [ ] Persistent volume POC, PodDisruptionBudget, rolling workloads, and etcd
      snapshots.
- [ ] Document a repeatable integration-test procedure for a disposable Mac.
- [ ] Archive the existing shim source Git commit, binary SHA-256, and daemon
      service configuration (see `docs/shim-setup.md`).

## Related documentation

- [Architecture](architecture.md) describes the implemented system design.
- [Operations runbook](runbook.md) documents the current operational workflow.
- [Release checklist](releasing.md) defines the publication gate.
