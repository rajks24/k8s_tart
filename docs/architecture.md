# Architecture and implementation

```text
                         macOS / M4 / 24 GiB RAM
+----------------------------------------------------------------+
|  Python k8sctl.py (stdlib)                                      |
|    |             |             |                    |             |
|  tart CLI        SSH+sudo      kubectl          state+logs       |
|    |             |             |                    |             |
|  Tart VZ         guest init    kubeadm API       .state/         |
|    |                           TCP 6443                           |
|  softnet binary (socket_vmnet shim, existing; PATH priority)   |
|    |                                                           |
|  socket_vmnet (existing, socket path from TOML)                |
+----+------------------------+-------------------------+---------+
     |                        |                         |
 k8s-cp Ubuntu           k8s-w1 Ubuntu            k8s-w2 Ubuntu
    2 CPU/6 GiB            2 CPU/4 GiB              2 CPU/4 GiB
  API+etcd+control         kubelet+Pods             kubelet+Pods
     |                        |                         |
     +----------- Flannel VXLAN /10.244.0.0/16--------+
```

Layers:

- **Tart**: Apple Virtualization.framework ARM64 Ubuntu VMs, running headless.
- **Shim**: existing installed binary translated to `socket_vmnet` stream socket.
- **VM NICs**: 192.168.105.0/24 (check live guest-agent IP; DHCP reservations urged).
- **containerd**: CRI; systemd cgroups; runs Kubernetes and user containers.
- **kubeadm**: creates control-plane PKI, static Pods and kubelet bootstrap config.
- **Flannel**: pinned release manifest; Pod CIDR 10.244.0.0/16; VXLAN over VM L2.
- **Kubernetes Service**: default service CIDR 10.96.0.0/12.
- **Client**: `KUBECONFIG=.state/kubeconfig` maintains isolation from other kubecontexts.

Config is TOML (Python 3.11 `tomllib`) to avoid Helm/Ansible/YAML parser
requirements for host automation. `k8sctl.py` imports only the standard library.

Idempotence boundaries:

- Existing VMs are neither resized nor recloned.
- Existing initialized kubeadm nodes skip preparation/init.
- Existing Flannel namespace skips installation rather than doing an upgrade.
- Existing joined workers skip token creation/join.
- IP address drift is fatal; automatically updating kubeadm PKI is forbidden.
- Destructive operations require explicit cluster-name confirmation.

**ARM64 matters:** all container images/add-ons must support `linux/arm64`.
No NVIDIA GPU is provided by this Apple Silicon VM stack.
