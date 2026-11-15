# Architecture and implementation

[Documentation index](README.md) · [Project README](../README.md)

```mermaid
flowchart LR
    accTitle: k8s-tart host and cluster architecture
    accDescr {
      k8sctl controls three Tart Ubuntu virtual machines through Tart, SSH,
      and kubectl. A Softnet compatibility shim connects their virtual
      interfaces to socket_vmnet. Flannel provides the Kubernetes Pod overlay.
    }

    subgraph host["macOS host · Apple Silicon"]
        direction TB
        cli["k8sctl.py<br/>Python 3.11+ standard library"]
        tart["Tart CLI<br/>Virtualization.framework"]
        shim["softnet compatibility shim<br/>Selected through PATH"]
        daemon["socket_vmnet daemon<br/>Socket path from cluster.toml"]
        admin["Cluster administration<br/>SSH + sudo · kubectl"]
        state["Local data<br/>.state · logs · reports"]

        cli --> tart --> shim --> daemon
        cli --> admin
        cli --> state
    end

    subgraph cluster["Tart Ubuntu ARM64 cluster"]
        direction TB
        endpoints["Shared VM network and endpoints<br/>192.168.105.0/24 · API :6443"]
        cp["k8s-cp · control plane<br/>2 CPU · 6 GiB<br/>API server · etcd"]
        worker1["k8s-w1 · worker<br/>2 CPU · 4 GiB<br/>kubelet · Pods"]
        worker2["k8s-w2 · worker<br/>2 CPU · 4 GiB<br/>kubelet · Pods"]
        pod_network["Flannel VXLAN Pod overlay<br/>10.244.0.0/16"]

        endpoints --> cp
        endpoints --> worker1
        endpoints --> worker2
        cp --- pod_network
        worker1 --- pod_network
        worker2 --- pod_network
    end

    daemon --> endpoints
    admin -.-> endpoints
```

Solid arrows show lifecycle or network attachment. The dotted arrow shows the
SSH and Kubernetes administration path. Undirected connections show that all
nodes participate in the same Flannel Pod overlay.

## Layers

- **Tart**: Apple Virtualization.framework ARM64 Ubuntu VMs, running headless.
- **Shim**: compatibility binary that translates Tart datagrams to the framed
  stream protocol used by `socket_vmnet`.
- **socket_vmnet**: root daemon that owns the macOS virtual network and exposes
  the Unix socket configured in `cluster.toml`.
- **VM NICs**: 192.168.105.0/24 (check the live guest-agent IP, DHCP
  reservations are urged).
- **containerd**: CRI, systemd cgroups, runs Kubernetes and user containers.
- **kubeadm**: creates control-plane PKI, static Pods, and kubelet bootstrap
  configuration.
- **Flannel**: pinned release manifest, Pod CIDR 10.244.0.0/16, VXLAN over the
  VM L2 network.
- **Kubernetes Service**: default service CIDR 10.96.0.0/12.
- **Client**: `.state/kubeconfig` remains isolated automation state, `k8sctl
context` can safely merge a namespaced entry into the normal client
  kubeconfig, with a backup and collision protection.

## Configuration

Config is TOML (Python 3.11 `tomllib`) to avoid Helm/Ansible/YAML parser
requirements for host automation. `k8sctl.py` imports only the standard library.

## Idempotence boundaries

- Existing VMs are neither resized nor recloned.
- Existing initialized kubeadm nodes skip preparation/init.
- Existing Flannel DaemonSet skips installation rather than doing an upgrade.
- Existing joined workers skip token creation/join.
- IP address drift is fatal and automatically updating kubeadm PKI is forbidden.
- Destructive operations require explicit cluster-name confirmation.

**ARM64 matters:** all container images/add-ons must support `linux/arm64`.
No NVIDIA GPU is provided by this Apple Silicon VM stack.

## Related documentation

- [Softnet shim setup](shim-setup.md) installs the host network components.
- [Networking](networking.md) explains DHCP, Flannel, and IP-drift handling.
- [Operations runbook](runbook.md) covers testing and recovery procedures.
