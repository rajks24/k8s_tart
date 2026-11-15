# Operations, testing, recovery

## Quick triage

```bash
cd ~/myprojects/k8s_tart
python3 k8sctl.py status
python3 k8sctl.py doctor
python3 k8sctl.py diagnose
```

Reports are saved at `reports/<timestamp>/`. They include macOS Tart state,
Linux node addresses/routes, containerd and kubelet service status/logs,
CRI containers, bridge devices, node/pod inventory and Flannel logs.
They **do not** intentionally include join tokens or admin kubeconfig, but
real logs can contain workload-sensitive details. Review before sharing.

## Inspect manually

```bash
export KUBECONFIG="$HOME/myprojects/k8s_tart/.state/kubeconfig"
kubectl get nodes -o wide
kubectl get pods -A -o wide
kubectl get events -A --sort-by=.lastTimestamp
kubectl get pods -n kube-flannel -o wide
kubectl get pods -n kube-system -o wide
kubectl logs -n kube-flannel -l app=flannel --all-containers --tail=150
kubectl get --raw /readyz
```

On a guest:

```bash
sudo systemctl status containerd kubelet
sudo journalctl -u kubelet --no-pager -n 200
sudo journalctl -u containerd --no-pager -n 200
sudo crictl --runtime-endpoint unix:///run/containerd/containerd.sock ps -a
sysctl net.ipv4.ip_forward
ip -4 route
ip -d link show flannel.1
```

| Fault | Layers/checks | Typical remediation |
|---|---|---|
| `preflight` shim missing | `/opt/tart-vmnet-shim/bin/softnet` and executable bit | Restore YOUR known-good binary; don't auto-reinstall |
| Missing daemon socket | `pgrep -fl socket_vmnet`, config socket path | Start your existing socket_vmnet service; don't switch network backends |
| VMs run but cannot ping | actual VM subnet, DHCP, bridge, firewall | Fix socket_vmnet/guest networking before kubeadm |
| `tart ip --resolver=agent` fails | Guest boot/agent service | Check `logs/<vm>.log`, Ubuntu guest agent |
| API unreachable | control-plane current IP, 6443, kubelet/etcd | Restore DHCP reservation; check static Pod logs |
| Worker NotReady | CNI, CRI, kubelet, Pod CIDR | Check Flannel, containerd and kubelet logs |
| Pod cross-node ping fails | VXLAN UDP 8472/route/firewall | Inspect flannel.1, guest firewalls and routes |
| DNS fails | CoreDNS, service rules, CNI | Check kube-system/CoreDNS and Endpoints |
| Test Pod cannot pull image | ARM64 image or registry | Use multiarch images; check DNS + egress |

## Restart after normal shutdown

```bash
python3 k8sctl.py start
python3 k8sctl.py status
python3 k8sctl.py test
```

An IP drift alert is **intentional protection**. Restore the original IP
lease/reservation before proceeding. See `networking.md`.

## Rebuild the lab from scratch

**Deletes data on all three VMs** if you choose `destroy`:

```bash
# First collect information/backup any workloads you want to keep
python3 k8sctl.py diagnose
python3 k8sctl.py destroy --yes --confirm tart-kubeadm-lab

# Recreate VM disks and boot them with your existing shim
python3 k8sctl.py create
python3 k8sctl.py start
python3 k8sctl.py access     # interactive once on new guests
python3 k8sctl.py up
python3 k8sctl.py test
```

To keep VM disks but reset just kubeadm state:

```bash
python3 k8sctl.py reset-k8s --yes --confirm tart-kubeadm-lab
python3 k8sctl.py up
```

A reset does not restore workloads, secrets, external disks or PV contents.
These commands are appropriate only for a disposable POC, NOT production.

## What not to automate

- No silent kubeadm reset/reinit of a working cluster.
- No automatic writing to `/etc/bootptab` on macOS.
- No automatic root-owned shim replacement or socket_vmnet service reinstall.
- No automatic Kubernetes version upgrade on already joined nodes.
- No auto-deleting non-POC Tart VMs, custom namespaces, or local containers.
