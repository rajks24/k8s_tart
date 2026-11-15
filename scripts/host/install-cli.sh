#!/usr/bin/env bash
# Install or remove a user-local `k8sctl` command pointing at this checkout.
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
SOURCE="$PROJECT_ROOT/k8sctl.py"
CONFIG="$PROJECT_ROOT/config/cluster.toml"
CLI_BIN_DIR="${K8SCTL_BIN_DIR:-$HOME/.local/bin}"
ACTION="${1:---install}"

usage() {
  echo "Usage: $0 [--install|--uninstall]" >&2
}

if [[ "$ACTION" != --install && "$ACTION" != --uninstall ]]; then
  usage
  exit 2
fi

command -v python3 >/dev/null 2>&1 || {
  echo "Python 3 is required. Install Python 3.11 or newer first." >&2
  exit 1
}
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || {
  echo "Python 3.11 or newer is required; found $(python3 --version 2>&1)." >&2
  exit 1
}
[[ -x "$SOURCE" ]] || {
  echo "CLI source is missing or not executable: $SOURCE" >&2
  exit 1
}

alias_output="$(python3 - "$CONFIG" <<'PY'
import re
import sys
import tomllib

with open(sys.argv[1], "rb") as stream:
    aliases = tomllib.load(stream).get("cluster", {}).get("cli_aliases", [])
if not isinstance(aliases, list) or not all(isinstance(item, str) for item in aliases):
    raise SystemExit("cluster.cli_aliases must be an array of command-name strings")
if len(set(aliases)) != len(aliases):
    raise SystemExit("cluster.cli_aliases contains duplicate command names")
for alias in aliases:
    if alias == "k8sctl" or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", alias):
        raise SystemExit(f"Unsafe or reserved CLI alias: {alias!r}")
    print(alias)
PY
)"
COMMAND_NAMES=(k8sctl)
while IFS= read -r command_name; do
  [[ -n "$command_name" ]] && COMMAND_NAMES+=("$command_name")
done <<< "$alias_output"

if [[ "$ACTION" == --uninstall ]]; then
  for command_name in "${COMMAND_NAMES[@]}"; do
    destination="$CLI_BIN_DIR/$command_name"
    [[ -e "$destination" || -L "$destination" ]] || continue
    if [[ ! -L "$destination" ]]; then
      echo "Refusing to remove $destination: it is not a symbolic link." >&2
      exit 1
    fi
    link_target="$(readlink "$destination")"
    if [[ "$link_target" != "$SOURCE" && "$link_target" != "$CLI_BIN_DIR/k8sctl" ]]; then
      echo "Refusing to remove $destination: it is not managed by this checkout." >&2
      exit 1
    fi
  done
  for command_name in "${COMMAND_NAMES[@]}"; do
    destination="$CLI_BIN_DIR/$command_name"
    if [[ -L "$destination" ]]; then
      rm "$destination"
      echo "Removed $destination"
    fi
  done
  exit 0
fi

mkdir -p "$CLI_BIN_DIR"
for command_name in "${COMMAND_NAMES[@]}"; do
  destination="$CLI_BIN_DIR/$command_name"
  if [[ -e "$destination" || -L "$destination" ]]; then
    link_target=""
    [[ -L "$destination" ]] && link_target="$(readlink "$destination")"
    if [[ "$link_target" != "$SOURCE" && "$link_target" != "$CLI_BIN_DIR/k8sctl" ]]; then
      echo "Refusing to overwrite existing command: $destination" >&2
      exit 1
    fi
  fi
done

for command_name in "${COMMAND_NAMES[@]}"; do
  destination="$CLI_BIN_DIR/$command_name"
  if [[ -L "$destination" && "$(readlink "$destination")" == "$SOURCE" ]]; then
    echo "Already installed: $destination -> $SOURCE"
  else
    [[ -L "$destination" ]] && rm "$destination"
    ln -s "$SOURCE" "$destination"
    echo "Installed $destination -> $SOURCE"
  fi
done

case ":$PATH:" in
  *":$CLI_BIN_DIR:"*) ;;
  *)
    echo
    echo "Add this directory to PATH in your shell profile:"
    echo "  export PATH=\"$CLI_BIN_DIR:\$PATH\""
    ;;
esac
echo "Run: k8sctl --version"
echo "Then: k8sctl preflight"
