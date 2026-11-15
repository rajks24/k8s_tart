#!/usr/bin/env bash
# Read-only host/VM inventory to aid DHCP MAC reservation work.
set -euo pipefail
printf '\n=== SHIM ===\n'
ls -l /opt/tart-vmnet-shim/bin/softnet 2>&1 || true
shasum -a 256 /opt/tart-vmnet-shim/bin/softnet 2>&1 || true
printf '\n=== SOCKET VMNET ===\n'
pgrep -fl socket_vmnet || true
printf '\n=== TART ===\n'
tart list
for name in k8s-cp k8s-w1 k8s-w2; do
  printf '\n=== %s ===\n' "$name"
  ip="$(tart ip --resolver=agent "$name" 2>/dev/null || true)"
  if [[ -z "$ip" ]]; then echo 'IP unavailable'; continue; fi
  echo "IP=$ip"
  ssh -o BatchMode=yes -o ConnectTimeout=7 "admin@$ip" \
    'dev=$(ip -4 route show default | awk "{print \$5;exit}"); echo "NIC=$dev"; cat "/sys/class/net/$dev/address"; ip -br -4 addr; ip -4 route' \
    || echo 'SSH not available; run k8sctl.py access or check your SSH key'
done
