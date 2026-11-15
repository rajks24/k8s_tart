# Install and configure the Softnet shim

[Documentation index](README.md) · [Project README](../README.md)

This guide is for a new Apple Silicon Mac with no existing Tart networking
setup. Complete it before creating any cluster VMs.

The network has three separate components:

```text
Tart VM -> softnet compatibility shim -> socket_vmnet daemon -> macOS vmnet
```

- Tart launches an executable named `softnet` for `--net-softnet` VMs.
- `socket-vmnet-shim` supplies that executable and translates Tart's traffic.
- `socket_vmnet` is the root daemon that owns the macOS virtual network and
  provides the Unix socket used by the shim.

The shim does not install or start `socket_vmnet`. `k8sctl` deliberately
treats both components as host prerequisites and never changes them during
cluster provisioning.

> **Security boundary:** the installation below creates a root-owned SUID
> shim. Review the pinned source before installing it. Do not use a binary
> built from an untrusted or locally modified checkout. The shim also ignores
> Softnet allow/block filters, so this network is not a security boundary.

## 1. Install the basic tools

```bash
xcode-select -p || xcode-select --install
```

Wait for Command Line Tools installation to finish. If Homebrew is not
installed, follow the current instructions at <https://brew.sh>, then verify
it in a new shell:

```bash
brew --version
brew install cirruslabs/cli/tart rust
tart --version
rustc --version
```

The rest of the project also requires Python 3.11+ and `kubectl`, see the
[host prerequisites](../README.md#host-prerequisites).

## 2. Install `socket_vmnet`

The recommended Tart-only layout uses the upstream release under
`/opt/socket_vmnet`, its system LaunchDaemon, gateway `192.168.105.1`, and
socket `/var/run/socket_vmnet`. Those values match the tracked
`config/cluster.toml` defaults.

Choose and review an upstream release before running these commands. Version
`1.2.2` was the current release pinned when this guide was last updated, do
not silently change the version in automation.

```bash
SOCKET_VMNET_VERSION=1.2.2
SOCKET_VMNET_ARCHIVE="socket_vmnet-${SOCKET_VMNET_VERSION}-$(uname -m).tar.gz"
SOCKET_VMNET_URL="https://github.com/lima-vm/socket_vmnet/releases/download/v${SOCKET_VMNET_VERSION}"
SOCKET_VMNET_DOWNLOAD="$(mktemp -d)"
cd "$SOCKET_VMNET_DOWNLOAD"

curl -fLO "$SOCKET_VMNET_URL/$SOCKET_VMNET_ARCHIVE"
curl -fLO "$SOCKET_VMNET_URL/SHA256SUMS"
grep " ${SOCKET_VMNET_ARCHIVE}$" SHA256SUMS | shasum -a 256 -c -

# Recommended: verify publisher provenance when the GitHub CLI is installed.
if command -v gh >/dev/null; then
  gh attestation verify --owner lima-vm "$SOCKET_VMNET_ARCHIVE"
else
  echo 'WARN: gh is unavailable, publisher attestation was not verified'
fi

# Inspect the archive paths before the privileged extraction.
tar tzf "$SOCKET_VMNET_ARCHIVE"
sudo tar -C / -xzvf "$SOCKET_VMNET_ARCHIVE" opt/socket_vmnet
```

The checksum detects a damaged or mismatched archive but, because it is
downloaded from the same release, is not independent proof of origin. The
GitHub artifact-attestation check provides publisher provenance. If `gh` is
unavailable, review the upstream release and decide whether its provenance is
sufficient before performing the privileged extraction.

Verify that the installed directory is not user-writable:

```bash
ls -ld /opt/socket_vmnet /opt/socket_vmnet/bin
ls -l /opt/socket_vmnet/bin/socket_vmnet
/opt/socket_vmnet/bin/socket_vmnet --version
```

The directories and executable should be owned by `root`. Do not install the
privileged daemon from a directory writable by an untrusted user.

## 3. Start the system LaunchDaemon

Install the plist included in the reviewed upstream archive:

```bash
SOCKET_VMNET_SERVICE=io.github.lima-vm.socket_vmnet
sudo install -d -o root -g wheel -m 0755 /var/log/socket_vmnet
sudo install -o root -g wheel -m 0644 \
  "/opt/socket_vmnet/share/doc/socket_vmnet/launchd/${SOCKET_VMNET_SERVICE}.plist" \
  "/Library/LaunchDaemons/${SOCKET_VMNET_SERVICE}.plist"
sudo plutil -lint "/Library/LaunchDaemons/${SOCKET_VMNET_SERVICE}.plist"
sudo launchctl bootstrap system "/Library/LaunchDaemons/${SOCKET_VMNET_SERVICE}.plist"
sudo launchctl enable "system/${SOCKET_VMNET_SERVICE}"
sudo launchctl kickstart -kp "system/${SOCKET_VMNET_SERVICE}"
```

`bootstrap` reports that the service is already loaded when it has previously
been installed. In that case, inspect it instead of repeatedly reinstalling
it:

```bash
sudo launchctl print system/io.github.lima-vm.socket_vmnet
pgrep -fl socket_vmnet
ls -l /var/run/socket_vmnet
```

The final path must be a Unix socket. With the upstream defaults it is owned
by `root`, accessible to the macOS `staff` group, and uses shared networking
with gateway `192.168.105.1`.

If the service does not start, inspect its error log before continuing:

```bash
sudo tail -n 100 /var/log/socket_vmnet/stderr
```

Do not create an ordinary file at the configured socket path and do not run a
second daemon against the same path.

## 4. Build and install the compatibility shim

Return to this project's checkout and clone the reviewed shim source into the
ignored `socket-vmnet-shim/` directory. The commit below is immutable and was
the upstream `main` commit pinned when this guide was updated.

```bash
cd ~/myprojects/k8s_tart
git clone https://github.com/tannevaled/socket-vmnet-shim.git
git -C socket-vmnet-shim checkout 7eee5b855774d567d9ac6656f2e1bd6436f0da94
git -C socket-vmnet-shim status --short
git -C socket-vmnet-shim rev-parse HEAD
```

The status output should be empty and the reported commit must equal the
requested commit. Review at least `Cargo.toml`, `Cargo.lock`, `src/main.rs`,
and the upstream security/limitations discussion before granting SUID root:

```bash
git -C socket-vmnet-shim show --stat --oneline HEAD
less socket-vmnet-shim/Cargo.toml
less socket-vmnet-shim/src/main.rs
```

Use this project's guarded helper to build and install the shim at the path
expected by `cluster.toml`:

```bash
scripts/host/restore-softnet-shim.sh --dry-run
scripts/host/restore-softnet-shim.sh --install
```

The install action requires the exact confirmation phrase displayed by the
script. It builds locally, preserves any existing destination as a timestamped
backup, and installs:

```text
/opt/tart-vmnet-shim/bin/softnet
```

Verify ownership, mode, and source provenance:

```bash
stat -f '%Su %Sg %Sp %N' /opt/tart-vmnet-shim/bin/softnet
shasum -a 256 /opt/tart-vmnet-shim/bin/softnet
git -C socket-vmnet-shim rev-parse HEAD
```

The binary should be `root:wheel`, executable, and have the SUID bit set
(`-rwsr-xr-x`). The containing `/opt/tart-vmnet-shim` directories must not be
writable by normal users.

## 5. Match `cluster.toml` to the daemon

For the recommended LaunchDaemon installation above, retain these values:

```toml
[network]
mode = "softnet"
softnet_bin = "/opt/tart-vmnet-shim/bin/softnet"
socket_path = "/var/run/socket_vmnet"
subnet = "192.168.105.0/24"
gateway = "192.168.105.1"
```

The `gateway` and `subnet` must describe the daemon's network. The
`socket_path` must identify the exact socket created by the running daemon.
TOML does not expand `$HOME`, command substitutions, or shell variables.

Other supported layouts require an explicit configuration change:

| Daemon layout                          | Typical socket path                         | Guidance                                                       |
| -------------------------------------- | ------------------------------------------- | -------------------------------------------------------------- |
| `/opt/socket_vmnet` LaunchDaemon       | `/var/run/socket_vmnet`                     | Recommended, matches defaults                                  |
| Root Homebrew service on Apple Silicon | `/opt/homebrew/var/run/socket_vmnet`        | Set `network.socket_path` to this absolute path                |
| Lima shared network                    | `/private/var/run/lima/socket_vmnet.shared` | Lima must keep the daemon running, set the exact observed path |

Do not choose a socket merely because it exists. Confirm which daemon owns it
with `sudo launchctl print`, `pgrep -fl socket_vmnet`, and its plist or process
arguments.

## 6. Run and interpret preflight

Install the CLI if needed, then run the read-only check:

```bash
cd ~/myprojects/k8s_tart
make install-cli
k8sctl preflight
```

If `k8sctl` is not found, apply the `PATH` line printed by the installer and
start a new shell (or source the updated shell profile) before retrying.

A ready installation resembles:

```text
==> Host / shim / socket preflight (read-only)
  tart         /opt/homebrew/bin/tart
  ssh          /usr/bin/ssh
  scp          /usr/bin/scp
  Tart version  2.x.x
  Softnet path   /opt/tart-vmnet-shim/bin/softnet
  PATH resolves  /opt/tart-vmnet-shim/bin/softnet
  Daemon socket  /var/run/socket_vmnet
  Socket connect OK (do not assume that this proves VM routing)
  Preflight OK
```

Preflight verifies:

- required host commands and the reported Tart version;
- that the configured shim exists and is executable;
- that Tart's child `PATH` resolves the configured shim, not another
  `softnet` executable;
- root/SUID mode (a warning is emitted when missing);
- that the configured path is a Unix socket and the current user can connect.

Preflight does **not** prove that the daemon uses the configured gateway or
subnet, that DHCP will assign an address, that a VM can reach the internet, or
that two VMs can exchange traffic. Those checks require running VMs.

After preflight succeeds, follow its `NEXT:` output:

```bash
k8sctl create
k8sctl start
k8sctl access
k8sctl up
k8sctl context use
k8sctl test
```

`k8sctl test` is the final proof of cross-node Pod networking, DNS, and
Service routing. See [networking.md](networking.md) for DHCP reservations and
layer-by-layer diagnosis.

## Preflight troubleshooting

| Output                                        | Cause                                                        | Correction                                                                         |
| --------------------------------------------- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| `Existing shim binary missing/not executable` | `softnet_bin` is wrong or installation was not completed     | Verify the source and rerun the guarded shim install, or correct the absolute path |
| `PATH chooses a different softnet executable` | Another `softnet` shadows the configured binary              | Correct `softnet_bin`, `k8sctl` prepends its parent directory automatically        |
| `shim is not root-owned SUID`                 | Ownership/mode does not meet Tart's expectation              | Re-audit the source, then reinstall with the guarded helper                        |
| `socket_vmnet socket missing/not a socket`    | Daemon stopped or `socket_path` describes a different layout | Inspect LaunchDaemon state and process arguments, use the exact live socket        |
| `Cannot connect to socket_vmnet socket`       | Socket permissions or daemon health problem                  | Check `ls -l`, group membership, daemon logs, and service state                    |
| Preflight passes but VM has no IP             | Daemon/DHCP/gateway mismatch or guest-agent issue            | Inspect daemon logs and `logs/<vm>.log`, compare the plist with `cluster.toml`     |
| VMs get IPs but cannot reach each other       | Wrong helper selected or daemon/shim compatibility problem   | Recheck the selected shim and run the layer checks in `networking.md`              |

## Existing installations and recovery

Do not replace a healthy shim or daemon merely to match this guide. First
capture the working state:

```bash
scripts/host/network-inventory.sh
shasum -a 256 /opt/tart-vmnet-shim/bin/softnet
stat -f '%Su %Sg %Sp %N' /opt/tart-vmnet-shim/bin/softnet
git -C socket-vmnet-shim rev-parse HEAD
sudo launchctl print system/io.github.lima-vm.socket_vmnet
```

Use `restore-softnet-shim.sh` only when the installed binary is missing,
corrupted, or intentionally being upgraded from reviewed source. It never
installs, starts, stops, or changes the `socket_vmnet` daemon.

Upstream references:

- [`socket-vmnet-shim` installation and limitations][shim-upstream]
- [`socket_vmnet` installation, LaunchDaemon, and usage][socket-upstream]
- [`socket_vmnet` release artifacts][socket-releases]

[shim-upstream]: https://github.com/tannevaled/socket-vmnet-shim
[socket-upstream]: https://github.com/lima-vm/socket_vmnet
[socket-releases]: https://github.com/lima-vm/socket_vmnet/releases

## Related documentation

- [Architecture](architecture.md) shows how the shim and daemon connect Tart
  to the Kubernetes nodes.
- [Networking](networking.md) covers DHCP reservations and connectivity checks
  after VMs are running.
- [Operations runbook](runbook.md) covers restart, diagnosis, and recovery.
