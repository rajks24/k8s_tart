#!/usr/bin/env bash
# Manual recovery tool, NEVER called by k8sctl.py. Read this script before use.
# Restores a shim from the already-present trusted local source tree.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE="${SHIM_SOURCE:-$ROOT/socket-vmnet-shim}"
DEST="${SHIM_DEST:-/opt/tart-vmnet-shim/bin/softnet}"
MODE="${1:---dry-run}"

if [[ "$MODE" != --dry-run && "$MODE" != --install ]]; then
  echo "Usage: $0 [--dry-run|--install]" >&2; exit 2
fi
if [[ ! -f "$SOURCE/Cargo.toml" ]]; then
  echo "Source not found: $SOURCE/Cargo.toml" >&2
  echo "Recover the previously reviewed shim source first; no automatic git clone." >&2
  exit 1
fi
printf 'Shim source: %s\nBinary destination: %s\nMode: %s\n' "$SOURCE" "$DEST" "$MODE"
printf 'NOTE: This installs a root-owned setuid binary. Review local source and build provenance!\n'
if [[ "$MODE" == --dry-run ]]; then
  echo 'DRY RUN: would execute cargo build --locked --release and install binary after explicit confirmation.'
  exit 0
fi
[[ "$(uname -s)" == Darwin ]] || { echo 'Only macOS supported' >&2; exit 1; }
command -v cargo >/dev/null || { echo 'Rust cargo required' >&2; exit 1; }
printf 'Type exactly REPLACE-SOFTNET to approve replacing the installed shim: '
read -r reply
[[ "$reply" == REPLACE-SOFTNET ]] || { echo 'Cancelled'; exit 1; }
( cd "$SOURCE" && cargo build --locked --release )
BIN="$SOURCE/target/release/softnet"
[[ -x "$BIN" ]] || { echo 'Build did not produce softnet binary' >&2; exit 1; }
sudo install -d -o root -g wheel -m 0755 "$(dirname "$DEST")"
if [[ -e "$DEST" ]]; then
  backup="${DEST}.bak.$(date +%Y%m%d-%H%M%S)"
  sudo cp -p "$DEST" "$backup"
  echo "Existing binary preserved at $backup"
fi
sudo install -o root -g wheel -m 4755 "$BIN" "$DEST"
ls -l "$DEST"
echo 'Shim installed. The socket_vmnet daemon was NOT changed or restarted.'
