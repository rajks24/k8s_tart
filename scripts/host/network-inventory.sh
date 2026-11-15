#!/usr/bin/env bash
# Read-only host/VM inventory to aid DHCP MAC reservation work.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
CONFIG="${K8SCTL_CONFIG:-$ROOT/config/cluster.toml}"

command -v python3 >/dev/null || { echo 'Python 3.11+ is required' >&2; exit 1; }
read_config() {
  python3 - "$CONFIG" "$1" <<'PY'
import sys
import tomllib

with open(sys.argv[1], "rb") as stream:
    config = tomllib.load(stream)
key = sys.argv[2]
if key == "ssh_user":
    print(config["cluster"]["ssh_user"])
elif key == "softnet_bin":
    print(config["network"]["softnet_bin"])
elif key == "vm_names":
    print("\n".join(config["vm"]))
PY
}

SSH_USER="$(read_config ssh_user)"
SOFTNET_BIN="$(read_config softnet_bin)"
VM_NAMES="$(read_config vm_names)"

printf '\n=== SHIM ===\n'
ls -l "$SOFTNET_BIN" 2>&1 || true
shasum -a 256 "$SOFTNET_BIN" 2>&1 || true
printf '\n=== SOCKET VMNET ===\n'
pgrep -fl socket_vmnet || true
printf '\n=== TART ===\n'
tart list
while IFS= read -r name; do
  [[ -n "$name" ]] || continue
  printf '\n=== %s ===\n' "$name"
  ip="$(tart ip --resolver=agent "$name" 2>/dev/null || true)"
  if [[ -z "$ip" ]]; then echo 'IP unavailable'; continue; fi
  echo "IP=$ip"
  ssh -o BatchMode=yes -o ConnectTimeout=7 "$SSH_USER@$ip" \
    'dev=$(ip -4 route show default | awk "{print \$5;exit}"); echo "NIC=$dev"; cat "/sys/class/net/$dev/address"; ip -br -4 addr; ip -4 route' \
    || echo 'SSH not available; run k8sctl.py access or check your SSH key'
done <<< "$VM_NAMES"
