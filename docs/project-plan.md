# Work backlog / project milestones

## Phase 1 — Adopt and baseline
- [ ] Copy project source to `~/myprojects/k8s_tart` alongside existing shim source.
- [ ] Review `config/cluster.toml` for real shim binary and daemon socket.
- [ ] Run `preflight`; correct only config inaccuracies, not the working network.
- [ ] Run `access` only if existing key + passwordless sudo are unavailable.
- [ ] Run `adopt`; verify 3 Kubernetes nodes Ready and kubeconfig stored in `.state/`.
- [ ] Run `diagnose` to capture a baseline report.

Acceptance: `kubectl get nodes` shows cp/w1/w2 Ready; no VM reinitialized.

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
- [ ] Test `up` again on existing lab; observe no reinstall/reset.
- [ ] On a disposable copy, test a destroy/create/bootstrap cycle.

Acceptance: fresh lab reaches 3 Ready nodes; smoke tests pass; teardown safe.

## Phase 4 — Improvement ideas
- [ ] Dedicated least-privilege SSH/sudo bootstrap image, replacing lab-wide NOPASSWD.
- [ ] Automated launchd lifecycle if Mac sleep/reboot behaviour is acceptable.
- [ ] CI/Ansible alternative when scaling beyond three guests.
- [ ] Cilium networking option (separate cluster), baseline policy testing.
- [ ] Local metrics-server + optional Prometheus/Grafana + resource alerts.
- [ ] Persistent volume POC, PodDisruptionBudget, rolling workloads, etcd snapshots.
- [ ] CI integration tests on disposable Mac runner (current CI runs offline checks).
- [ ] Archive the existing shim source Git commit, binary SHA-256 and daemon service configuration (see `docs/shim-setup.md`).
