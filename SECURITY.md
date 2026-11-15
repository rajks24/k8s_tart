# Security policy

## Supported versions

Security fixes are applied to the latest release and the `main` branch. This
project automates a disposable personal Kubernetes lab and is not supported
for production, multi-user, or internet-exposed clusters.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability and do not attach
kubeconfigs, private keys, bootstrap tokens, or unreviewed diagnostic bundles.
Use GitHub's **Security → Report a vulnerability** private reporting flow.
If private vulnerability reporting is not yet enabled, contact the repository
owner privately through their GitHub profile without including exploit details
in a public message.

Include affected versions, impact, reproduction steps, and a proposed fix when
available. You should receive an acknowledgement within seven days.

## Security boundaries

- `k8sctl access` installs a lab-only `NOPASSWD: ALL` sudo rule in configured
  guests. Do not use it on production or shared machines.
- `restore-softnet-shim.sh --install` builds local source and installs a
  root-owned setuid executable. It is manual-only and requires source review.
- Runtime kubeconfigs, logs, reports, and cached manifests can contain
  sensitive information and are excluded from Git. Review them before sharing.
- The tool protects initialized kubeadm state from implicit reset, but explicit
  `reset-k8s` and `destroy` confirmations permanently remove lab state.

Never report real credentials. Revoke exposed credentials before reporting.
