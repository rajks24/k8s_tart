#!/usr/bin/env bash
# Idempotent *initial* guest preparation. Existing initialized nodes are skipped
# by the macOS orchestrator. Never upgrade kubeadm/kubelet on a live cluster.
set -Eeuo pipefail
NODE="${1:?expected node name}"; K8S_MINOR="${2:?expected Kubernetes minor}"
export DEBIAN_FRONTEND=noninteractive

echo "==> Preparing $NODE for Kubernetes $K8S_MINOR ($(uname -m))"
if [[ $(uname -m) != aarch64 ]]; then echo 'Expected Ubuntu ARM64' >&2; exit 1; fi
if [[ -e /etc/kubernetes/admin.conf || -e /etc/kubernetes/kubelet.conf ]]; then
  echo 'Node is already joined/initialized; refusing to alter the running setup' >&2
  exit 2
fi
hostnamectl set-hostname "$NODE"
if grep -qE '^127\.0\.1\.1[[:space:]]' /etc/hosts; then
  sed -i -E "s/^127\.0\.1\.1[[:space:]].*/127.0.1.1 $NODE/" /etc/hosts
else
  printf '127.0.1.1 %s\n' "$NODE" >> /etc/hosts
fi
swapoff -a
sed -i.bak -E '/^[^#].*[[:space:]]swap[[:space:]]/s/^/#/' /etc/fstab
cat >/etc/modules-load.d/k8s-tart.conf <<'MODS'
overlay
br_netfilter
MODS
modprobe overlay
modprobe br_netfilter
cat >/etc/sysctl.d/99-k8s-tart.conf <<'SYSCTL'
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1
SYSCTL
sysctl --system >/dev/null
apt-get update
apt-get install -y ca-certificates curl gpg apt-transport-https containerd openssh-server
mkdir -p /etc/containerd
if [[ ! -s /etc/containerd/config.toml ]]; then
  containerd config default >/etc/containerd/config.toml
fi
# containerd 1.x and 2.x support this setting under their respective plugin sections.
# Do not erase other containerd configuration.
if ! grep -q 'SystemdCgroup = true' /etc/containerd/config.toml; then
  if grep -q 'SystemdCgroup = false' /etc/containerd/config.toml; then
    sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g' /etc/containerd/config.toml
  else
    echo 'ERROR: no SystemdCgroup setting found; inspect containerd config manually.' >&2
    exit 3
  fi
fi
# Ubuntu packages can disable CRI. An active CRI plugin is required by kubeadm.
if grep -qE '^disabled_plugins\s*=.*"cri"' /etc/containerd/config.toml; then
  sed -i -E '/^disabled_plugins\s*=/s/"cri"//g; /^disabled_plugins\s*=/s/,\s*\]/]/g' /etc/containerd/config.toml
fi
systemctl enable --now containerd
systemctl restart containerd
systemctl enable --now ssh
mkdir -p -m 755 /etc/apt/keyrings
curl -fsSL "https://pkgs.k8s.io/core:/stable:/${K8S_MINOR}/deb/Release.key" \
  | gpg --dearmor --yes -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
printf 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/%s/deb/ /\n' "$K8S_MINOR" \
  >/etc/apt/sources.list.d/kubernetes.list
apt-get update
apt-get install -y kubelet kubeadm kubectl
apt-mark hold kubelet kubeadm kubectl
systemctl enable kubelet

echo '==> Post-install checks'
[[ -z "$(swapon --noheadings --show)" ]] || { echo 'Swap remains active' >&2; exit 4; }
[[ "$(sysctl -n net.ipv4.ip_forward)" == 1 ]] || exit 5
systemctl is-active --quiet containerd || exit 6
kubeadm version -o short
containerd --version
printf 'Prepared %s successfully\n' "$NODE"
