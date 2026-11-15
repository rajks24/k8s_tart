# Networking: Tart -> shim -> socket_vmnet -> kubeadm

## Working network topology

```text
Mac M4
 ├── Tart process k8s-cp ── softnet shim ──┐
 ├── Tart process k8s-w1 ── softnet shim ──┼── socket_vmnet daemon
 └── Tart process k8s-w2 ── softnet shim ──┘       |
                                              vmnet.framework shared L2
                                              192.168.105.0/24
                                              gw: 192.168.105.1
                                                     |
                                              all guest VMs
                                                     |
                                              Flannel VXLAN (UDP 8472)
                                              Pods: 10.244.0.0/16
```

The project preserves `/opt/tart-vmnet-shim/bin/softnet` exactly as found.
It prepends `/opt/tart-vmnet-shim/bin` to PATH for each `tart run`, and sets
`SOCKET_VMNET_PATH` on that child process. This is required because Tart
resolves the executable named `softnet` through PATH. The shim is not the
`socket_vmnet` daemon; the daemon must already be running.

The upstream shim documentation notes limitations: packet filtering flags
such as `--net-softnet-allow` are ignored, and loss of the daemon's socket
requires restarting VM networking. Do not use this shim to assert isolation.

## Verify the existing daemon and shim (no modifications)

```bash
ls -l /opt/tart-vmnet-shim/bin/softnet
stat -f '%Su %Sp %N' /opt/tart-vmnet-shim/bin/softnet
pgrep -fl socket_vmnet
ls -l /private/var/run/lima/socket_vmnet.shared
python3 k8sctl.py preflight
```

If your daemon uses `/var/run/socket_vmnet` or another location, update only
`network.socket_path` in `config/cluster.toml`; do **not** reinstall the
working daemon just because the default path differs.

## Existing IPs last observed in the reference discussion

| VM | Observed (example, may change) |
|---|---|
| k8s-cp | 192.168.105.4 |
| k8s-w1 | 192.168.105.2 |
| k8s-w2 | 192.168.105.3 |

Current IPs MUST be discovered using `tart ip --resolver=agent`.
Your control plane may still carry its last IP in:

```bash
sudo grep -- '--advertise-address' /etc/kubernetes/manifests/kube-apiserver.yaml
sudo grep 'server:' /etc/kubernetes/admin.conf
```

Never just replace a worker join address while a control plane certificate
still describes an old API endpoint.

## Strongly recommended: DHCP reservations BEFORE repeated reboots

**For the existing healthy cluster, reserve the IPs it uses TODAY** to avoid
resetting it. For a fresh lab, you can pick new unused addresses in
192.168.105.0/24. `socket_vmnet` documents `/etc/bootptab` reservations.

1. Discover the guest network interface's **actual VM MAC address**, not
   the daemon interface MAC:

```bash
for vm in k8s-cp k8s-w1 k8s-w2; do
  ip=$(tart ip --resolver=agent "$vm")
  echo "$vm $ip"
  ssh admin@"$ip" 'dev=$(ip -4 route show default | awk "{print \$5; exit}"); echo "NIC=$dev"; cat "/sys/class/net/$dev/address"'
done
```

2. Back up `/etc/bootptab` (if it exists). This file is system-wide and may
   include other VMs; NEVER overwrite reservations belonging to other tools.

```bash
sudo cp -p /etc/bootptab "/etc/bootptab.bak.$(date +%Y%m%d-%H%M%S)" \
  2>/dev/null || true
sudo nano /etc/bootptab
```

3. Ensure its `%%` header is present; **append** entries like these with the
   MACs observed above (replace the example MACs with real values):

```text
%%
# hostname  hwtype  MAC                reserved-IP
k8s-cp      1      aa:bb:cc:dd:ee:01  192.168.105.4
k8s-w1      1      aa:bb:cc:dd:ee:02  192.168.105.2
k8s-w2      1      aa:bb:cc:dd:ee:03  192.168.105.3
```

If your existing file already has `%%`, **do not add a second header**.

4. Reload macOS bootpd:

```bash
sudo /bin/launchctl kickstart -kp system/com.apple.bootpd
```

5. Confirm the reservations after a planned VM restart, **before** changing
   `reserved_ip` in the project config. If Ubuntu emits a DUID instead of a
   MAC-address-based DHCP identifier, check Netplan's `dhcp-identifier: mac`
   option for the actual DHCP interface. Make that change carefully on a VM
   console because incorrect Netplan config can disrupt SSH access.

6. Once reservations work, set each `[vm."..."] reserved_ip = "..."` in
   `config/cluster.toml`. The automation checks each expected address.

The above does not assume Tart exposes the VM MAC in `tart get --format=json`;
it obtains the actual address from the Linux guest NIC.

## Check all layers in order

```bash
# 1. Daemon/socket and Tart VM state
python3 k8sctl.py preflight
tart list

# 2. Host-side resolved addresses
tart ip --resolver=agent k8s-cp
tart ip --resolver=agent k8s-w1
tart ip --resolver=agent k8s-w2

# 3. Guest-to-guest ICMP / overlay, from a worker
ssh admin@192.168.105.2 'ping -c 3 192.168.105.4'

# 4. Kubernetes topology and cross-worker test
python3 k8sctl.py doctor
python3 k8sctl.py test
```

`preflight` checks that Tart sees your *installed* shim via its prefixed
PATH, that the `socket_vmnet` socket exists, and that a local Unix socket
connection can be established. It does not start/restart daemons or change
networking.

## If an IP changes

`status` shows `!!! IP DRIFT`; `start`, `adopt`, `up` and `reset-k8s`
refuse to continue if addresses differ from `.state/node_ips.json`.

Preferred fix: restore the original guest IP via DHCP reservation and restart
the guest. If you intentionally need new addresses, treat that as a **new
cluster deployment**, or perform a deliberate kubeadm control-plane endpoint
migration involving certificates, kubeconfigs and control-plane manifests.
Do not just edit the state file to suppress the guard.

Read: https://github.com/lima-vm/socket_vmnet#how-to-reserve-dhcp-addresses
Read: https://github.com/tannevaled/socket-vmnet-shim
