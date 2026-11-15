# Existing Softnet shim: archive and optional restoration

**Your working shim and socket_vmnet daemon are treated as prerequisites.**
We do not install/reinstall/reconfigure them during normal cluster provisioning.
The existing installed binary is:

```text
/opt/tart-vmnet-shim/bin/softnet
```

If the previously cloned shim source is in your project directory:

```text
~/myprojects/k8s_tart/socket-vmnet-shim/
```

keep it there. `scripts/host/restore-softnet-shim.sh` is an explicit,
**manual**, guarded rebuild-and-install helper. It does not manage the daemon.

## Capture current working state

```bash
cd ~/myprojects/k8s_tart
scripts/host/network-inventory.sh
shasum -a 256 /opt/tart-vmnet-shim/bin/softnet
stat -f '%Su %Sp %N' /opt/tart-vmnet-shim/bin/softnet
ls -l /private/var/run/lima/socket_vmnet.shared
```

Record the shim source Git commit if source is present:

```bash
git -C socket-vmnet-shim rev-parse HEAD
```

## Recover only if the binary is missing or corrupted

Review the source first and run dry-run:

```bash
scripts/host/restore-softnet-shim.sh --dry-run
```

Only after review, if you explicitly need it:

```bash
scripts/host/restore-softnet-shim.sh --install
```

This builds from `socket-vmnet-shim/` using Rust Cargo and installs a
root-owned SUID executable at `/opt/tart-vmnet-shim/bin/softnet`. Installation
backs up an existing executable. It does NOT install, start, stop or alter
the `socket_vmnet` daemon and has no effect on existing VM disks.

**Security:** SUID root executables can be dangerous if their source or
containing directories are untrusted. Review provenance, retain root-owned
non-user-writable destination directories and only use this recovery command
in your personal lab. The shim also omits Softnet's packet filters.

Source and technical limitations:
https://github.com/tannevaled/socket-vmnet-shim
https://github.com/lima-vm/socket_vmnet
