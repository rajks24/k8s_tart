# Kubernetes on Tart + socket_vmnet (Apple Silicon)

Repeatable **3-node ARM64 kubeadm lab** for an M4 Mac. Run `python3 k8sctl.py` from
`~/myprojects/k8s_tart` to adopt your existing lab or provision a new one.

**YOUR EXISTING LAB COMES FIRST:** `adopt`, `status`, `doctor`, and `diagnose`
are non-destructive. `up` creates missing VMs / joins missing nodes, but
**will not reset an initialized control plane**. `reset-k8s` and `destroy`
require an explicit typed confirmation flag. Nothing manages, reinstalls,
deletes, or alters `/opt/tart-vmnet-shim/bin/softnet` or `socket_vmnet`.

## Folder structure

```text
k8s_tart/
├── k8sctl.py                       # Main Mac automation CLI
├── config/cluster.toml             # All cluster/VM/shim parameters
├── scripts/guest/prepare-node.sh   # Idempotent uninitialized-Ubuntu preparation
├── docs/
│   ├── architecture.md             # Stack and flows
│   ├── networking.md               # Shim, daemon and DHCP/IP drift runbook
│   ├── runbook.md                  # Rebuild, repair and troubleshooting
│   └── project-plan.md             # Work backlog and acceptance criteria
├── tests/test_lab.py               # Offline safety/config unit tests
├── .github/workflows/validate.yml # CI static validation
├── vendor/README.md                # Pinned Flannel manifest cached on use
├── Makefile                        # Optional short commands
├── .gitignore                      # Kubeconfigs, state, reports, logs excluded
├── .state/                         # Automatically created: recorded IPs, kubeconfig
├── logs/                           # Automatically created: background Tart logs
└── reports/                        # Automatically created: diagnostic snapshots
```

If your existing `socket-vmnet-shim/` source directory is already inside
`~/myprojects/k8s_tart`, **leave it there**. This project does not touch it.
It assumes your working shim is installed at the path in the TOML file.

## Host prerequisites

- Apple Silicon Mac with Tart installed; all VMs Ubuntu ARM64.
- Python **3.11+** (`python3 --version`, or `brew install python`). No PyPI packages.
- `kubectl` on the Mac (`brew install kubectl`) for API management and smoke tests.
- Existing functional `socket_vmnet` daemon and compatible `softnet` shim.
- OpenSSH client and SSH keys for the Ubuntu `admin` account.
- For fully unattended guest provisioning, `admin` must have passwordless sudo
  **on lab VMs only**. The interactive `access` helper can set this up.
- VM networking reachable at `192.168.105.0/24` by default; edit config if not.
- Sufficient memory/storage: 2 vCPU/6 GiB CP, 2 vCPU/4 GiB per worker.

## First use with your *currently working* cluster

```bash
cd ~/myprojects/k8s_tart
python3 --version
python3 k8sctl.py preflight
python3 k8sctl.py status

# If SSH public keys or passwordless sudo are not configured on the VMs:
python3 k8sctl.py access  # INTERACTIVE; changes guest authorized_keys + sudoers

# Read-only Kubernetes adoption (downloads existing admin.conf, saves IP state):
python3 k8sctl.py adopt

# No rebuild: inspect and run temporary cluster smoke tests
python3 k8sctl.py doctor
python3 k8sctl.py test
python3 k8sctl.py diagnose
```

**Adoption needs SSH and sudo permissions.** The `access` step is *not*
read-only: it appends an SSH public key and installs a permissive `admin`
sudoers entry on the three lab VMs. Use only on your isolated personal lab.
You can do equivalent SSH/sudo setup manually and skip `access`.

`adopt` validates `admin.conf`'s API endpoint against the control-plane IP,
fetches the config securely to `.state/kubeconfig`, and records node IPs into
`.state/node_ips.json`. It **does not run kubeadm init/reset**.

Use the lab kubeconfig explicitly (won't overwrite your OrbStack contexts):

```bash
export KUBECONFIG="$HOME/myprojects/k8s_tart/.state/kubeconfig"
kubectl get nodes -o wide
kubectl get pods -A
```

## Full fresh cluster provisioning (once the shim/socket is already working)

```bash
# Set your image, VM resources, Kubernetes minor version, socket path, etc.
vi config/cluster.toml

# Optional: one-time guest access bootstrap after VMs exist
python3 k8sctl.py create
python3 k8sctl.py start
python3 k8sctl.py access

# Full automation (safe on already-initialized nodes; not a cluster upgrader)
python3 k8sctl.py up
python3 k8sctl.py test
```

`up` is designed to be re-runnable and checks for existing kubeadm files;
it never forces a control-plane reinit. For **completely hands-off provisioning
from scratch**, preconfigure SSH key access and passwordless sudo in a
reusable Ubuntu base image, or run the `access` command once after creating
new VMs. Standard upstream Ubuntu images require a first-login bootstrap.

Provision steps: `preflight -> clone missing VMs -> tart run --net-softnet ->
agent IP + drift guard -> SSH/guest TCP checks -> Linux/containerd/K8s prep ->
kubeadm init if missing -> Flannel if missing -> worker joins if missing ->
wait for node Ready`.

### Command reference

| Command | Effect | Destructive? |
|---|---|---|
| `preflight` | Tart/shim/socket/dependency checks | No |
| `access` | Add SSH key and guest passwordless sudo | Changes guest access |
| `adopt` | Register existing healthy cluster, copy kubeconfig | No change to VMs/K8s |
| `create` | Clone and size only missing VMs | Creates VMs |
| `start` | Start stopped VMs with shim; IP drift check | No reset |
| `up` | Reconcile new/missing Kubernetes components | Changes missing components |
| `status` | VM IP/state, Kubernetes nodes and nonrunning Pods | No |
| `doctor` | Read-only host, guest and Kubernetes health checks | No |
| `diagnose` | Save detailed read-only logs under reports/ | No |
| `test` | Temporary BusyBox/NGINX namespace; delete on exit | Transient test resources |
| `monitor --interval 30` | Continuous health polling | No |
| `stop` | Stop 3 VMs, retain disks/data | Stops compute |
| `reset-k8s --yes --confirm tart-kubeadm-lab` | Reset kubeadm/CNI on all guests | **YES: destroys cluster state** |
| `destroy --yes --confirm tart-kubeadm-lab` | Stop and delete the 3 Tart VMs | **YES: destroys VM disks** |

Convenience: `make status`, `make doctor`, `make up`, `make monitor`, `make test`.
Destructive Make targets still require explicit flags, so prefer the direct CLI.

## Day-2 lifecycle

```bash
python3 k8sctl.py status
python3 k8sctl.py monitor --interval 30 --count 10
python3 k8sctl.py diagnose
python3 k8sctl.py stop
python3 k8sctl.py start
python3 k8sctl.py status
```

Stopping and starting the VM **does not guarantee** the same DHCP IP. We
record the initial mapping and abort operations if a restarted VM's IP drifts.
Set up MAC-based DHCP reservations **for the currently working addresses**
if you wish to keep this cluster for long-term repeated starts. See
[docs/networking.md](docs/networking.md).

## What the smoke test covers

1. Runs BusyBox Pods pinned to each worker; verifies both are `Ready`.
2. Pings from one worker's Pod to the other worker's Pod (Flannel VXLAN).
3. Resolves Kubernetes service DNS from inside a Pod (CoreDNS).
4. Deploys NGINX and requests it through a ClusterIP Service (kube-proxy).
5. Removes the temporary namespace by default (`--keep` retains it).

The smoke test changes temporary resources, not your existing applications.
It requires all nodes healthy and outbound image registry access.

## Safe removal

To delete Kubernetes while **keeping Ubuntu VMs and shim**:

```bash
python3 k8sctl.py reset-k8s --yes --confirm tart-kubeadm-lab
```

To delete **only the 3 named Tart VMs**, leaving the existing shim, daemon,
other Tart VMs, cached images, project source and logs untouched:

```bash
python3 k8sctl.py destroy --yes --confirm tart-kubeadm-lab
```

`reset-k8s` does not remove Ubuntu packages, containerd or persistent data
outside kubeadm's standard state and CNI paths. It is **not** a complete
sanitization procedure. `destroy` removes the three named VM disks. Neither
command uninstalls Tart, removes the shim or stops `socket_vmnet`.

## Tests and development

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile k8sctl.py
bash -n scripts/guest/prepare-node.sh
```

The local unit tests do not need an Apple Mac or a running Kubernetes cluster.
The smoke test **does** operate on a live Kubernetes cluster.

## Known constraints

- This is a **single-control-plane lab** with no etcd HA or node redundancy.
- `up` is **not** a Kubernetes upgrade or disaster-recovery engine.
- IP drift is reported, **not** automatically repaired. Repairing kubeadm
  endpoint/certificates/etcd membership can be destructive; see networking doc.
- The shim does not enforce normal Softnet allow/block packet filtering. Treat
  these VMs as being on a shared L2 network; don't expose sensitive services.
- `SOCKET_VMNET_PATH` is passed only to Tart child processes, not changed
  globally in your login shell.
- The first machine-image provisioning needs network access for Ubuntu APT,
  Kubernetes packages, container images and the pinned Flannel manifest.
- Tested offline for Python syntax/config/unit tests. **Mac/Tart end-to-end
  execution cannot be tested in this execution environment**; validate on the
  actual Mac before treating automation as fully production-ready.

See [runbook](docs/runbook.md), [networking](docs/networking.md), and
[project roadmap](docs/project-plan.md).

## Existing shim source and recovery

The project includes `scripts/host/network-inventory.sh` to capture shim
checksums, VM IPs and guest NIC MACs. A **manual-only** recovery script
`scripts/host/restore-softnet-shim.sh` can rebuild the previously reviewed
`socket-vmnet-shim/` source and reinstall the binary if needed. It is never
invoked by `up` or `start`. See [shim setup](docs/shim-setup.md).

## Create a local Git repository (optional)

```bash
cd ~/myprojects/k8s_tart
git init
# Confirm your pre-existing socket-vmnet-shim checkout and runtime credentials
# are excluded by .gitignore.
git status --short
git add README.md VERSION Makefile k8sctl.py config docs scripts tests vendor .github .gitignore
git commit -m "Initial Tart kubeadm lab automation"
```

Git initialization is deliberately not automated because this directory may
already contain a separate `socket-vmnet-shim/` Git checkout or your own work.
