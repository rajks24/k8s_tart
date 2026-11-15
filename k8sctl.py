#!/usr/bin/env python3
"""Tart + socket_vmnet + kubeadm lab orchestrator. Python 3.11+, stdlib only.

Treat already-initialized VMs as external state: adoption and diagnostics never
reset nodes, reconfigure CNI, or change the existing softnet/socket_vmnet setup.
"""
from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import time
import tomllib
import urllib.request

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config" / "cluster.toml"
STATE = ROOT / ".state"
LOGS = ROOT / "logs"
REPORTS = ROOT / "reports"
KUBECONFIG = STATE / "kubeconfig"
IPS_FILE = STATE / "node_ips.json"
PREP = ROOT / "scripts" / "guest" / "prepare-node.sh"


class LabError(Exception):
    pass


def out(message: str) -> None:
    print(message, flush=True)


def write_secret(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(data)
    os.chmod(path, 0o600)


def call(args: list[str], *, input_text: str | None = None,
         check: bool = True, timeout: int | None = None,
         env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    try:
        p = subprocess.run(args, input=input_text, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LabError(f"Command failed: {args[0]}: {exc}") from exc
    if check and p.returncode:
        # Avoid exposing credentials embedded in commands (e.g. worker join token).
        detail = (p.stderr or p.stdout).strip()[-1200:]
        raise LabError(f"{args[0]} exited {p.returncode}: {detail}")
    return p


def cmd_output(args: list[str], timeout: int = 30) -> str:
    return call(args, timeout=timeout).stdout.strip()


class Lab:
    def __init__(self, config_file: Path = CONFIG_FILE):
        if sys.version_info < (3, 11):
            raise LabError("Python >= 3.11 required; try `brew install python`.")
        with config_file.open("rb") as f:
            config = tomllib.load(f)
        self.cluster = config["cluster"]
        self.net = config["network"]
        self.vms = config["vm"]
        self.name = self.cluster["name"]
        self.cp = next((name for name, info in self.vms.items()
                        if info["role"] == "control-plane"), None)
        self.workers = [name for name, info in self.vms.items()
                        if info["role"] == "worker"]
        if not self.cp or not self.workers:
            raise LabError("Configure one control plane and at least one worker.")
        subnet = ipaddress.ip_network(self.net["subnet"], strict=False)
        if subnet.version != 4:
            raise LabError("VM subnet must be IPv4.")
        self.subnet = subnet
        pod = ipaddress.ip_network(self.cluster["pod_cidr"])
        svc = ipaddress.ip_network(self.cluster["service_cidr"])
        if pod.overlaps(subnet) or svc.overlaps(subnet) or pod.overlaps(svc):
            raise LabError("VM, pod, and service networks must not overlap.")
        self.key = Path(self.cluster["ssh_private_key"]).expanduser()
        self.ssh_user = self.cluster["ssh_user"]
        for n, info in self.vms.items():
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", n):
                raise LabError(f"Unsafe VM name: {n}")
            desired = info.get("reserved_ip", "")
            if desired and ipaddress.ip_address(desired) not in subnet:
                raise LabError(f"Reserved IP {desired} for {n} outside {subnet}")
        for directory in (STATE, LOGS, REPORTS):
            directory.mkdir(exist_ok=True, mode=0o700)
        os.chmod(STATE, 0o700)

    def net_env(self) -> dict[str, str]:
        env = os.environ.copy()
        executable = Path(self.net["softnet_bin"])
        env["PATH"] = str(executable.parent) + os.pathsep + env.get("PATH", "")
        env["SOCKET_VMNET_PATH"] = self.net["socket_path"]
        return env

    def preflight(self, strict: bool = True) -> bool:
        out("==> Host / shim / socket preflight (read-only)")
        errors = []
        for executable in ("tart", "ssh", "scp"):
            path = shutil.which(executable)
            out(f"  {executable:12s} {path or 'MISSING'}")
            if not path:
                errors.append(f"Missing executable: {executable}")
        if shutil.which("tart"):
            try:
                out("  Tart version  " + cmd_output(["tart", "--version"]))
            except LabError as exc:
                out(f"  WARN: {exc}")
        softnet = Path(self.net["softnet_bin"])
        selected = shutil.which("softnet", path=self.net_env()["PATH"])
        out(f"  Softnet path   {softnet}")
        out(f"  PATH resolves  {selected or 'MISSING'}")
        if not softnet.is_file() or not os.access(softnet, os.X_OK):
            errors.append(f"Existing shim binary missing/not executable: {softnet}")
        if selected and os.path.realpath(selected) != os.path.realpath(softnet):
            errors.append("PATH chooses a different softnet executable")
        if softnet.exists():
            mode = softnet.stat()
            if mode.st_uid != 0 or not (mode.st_mode & stat.S_ISUID):
                out("  WARN: shim is not root-owned SUID; Tart may prompt for sudo")
        sock = Path(self.net["socket_path"])
        out(f"  Daemon socket  {sock}")
        if not sock.exists() or not stat.S_ISSOCK(sock.stat().st_mode):
            errors.append(f"socket_vmnet socket missing/not a socket: {sock}")
        else:
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                    connection.settimeout(2)
                    connection.connect(str(sock))
                out("  Socket connect OK (do not assume that this proves VM routing)")
            except OSError as exc:
                errors.append(f"Cannot connect to socket_vmnet socket: {exc}")
        if not self.key.is_file():
            out(f"  WARN: SSH key missing: {self.key} (run `access` if needed)")
        if errors:
            for message in errors:
                out("  ERROR: " + message)
            if strict:
                raise LabError("Preflight failed; fix the above without changing your working shim setup.")
        else:
            out("  Preflight OK")
        return not errors

    def vm_info(self, name: str) -> dict | None:
        result = call(["tart", "get", "--format=json", name], check=False, timeout=15)
        if result.returncode != 0:
            return None
        try:
            return json.loads(result.stdout)
        except ValueError as exc:
            raise LabError(f"Could not read Tart info for {name}: {exc}") from exc

    def create(self) -> None:
        self.preflight()
        for name, vm in self.vms.items():
            if self.vm_info(name) is not None:
                out(f"SKIP {name}: VM already exists; not changing its resources")
                continue
            image = self.cluster["ubuntu_image"]
            out(f"==> Clone {image} -> {name}")
            call(["tart", "clone", image, name], timeout=1800)
            call(["tart", "set", name,
                  "--cpu", str(vm["cpu"]),
                  "--memory", str(vm["memory_mib"]),
                  "--disk-size", str(vm["disk_gib"])], timeout=60)
            out(f"Created {name}")

    def start(self, check_preflight: bool = True) -> None:
        if check_preflight:
            self.preflight()
        for name in self.vms:
            info = self.vm_info(name)
            if info is None:
                raise LabError(f"VM {name} absent. Run `create` or `up` first.")
            if info.get("Running") is True:
                out(f"SKIP {name}: already running")
                continue
            logfile = LOGS / f"{name}.log"
            with logfile.open("ab") as log:
                out(f"==> Starting {name} with existing softnet shim -> {logfile}")
                subprocess.Popen(["tart", "run", "--no-graphics", "--net-softnet", name],
                                 stdin=subprocess.DEVNULL, stdout=log,
                                 stderr=subprocess.STDOUT,
                                 env=self.net_env(), start_new_session=True)
        # Check for changed IPs after all machines have had time to start.
        ips = self.discover_ips()
        self.guard_ips(ips)
        out("All VM addresses discovered. Run `status` or `up`.")

    def discover_ips(self) -> dict[str, str]:
        timeout = int(self.cluster["ip_wait_seconds"])
        ips = {}
        for name in self.vms:
            out(f"==> Waiting for agent IP: {name}")
            end = time.monotonic() + timeout
            last_error = ""
            while time.monotonic() < end:
                result = call(["tart", "ip", "--resolver=agent", name],
                              check=False, timeout=15)
                raw = result.stdout.strip().splitlines()
                if result.returncode == 0 and raw:
                    try:
                        ip = str(ipaddress.ip_address(raw[-1].strip()))
                        if ipaddress.ip_address(ip) not in self.subnet:
                            raise LabError(f"{name} IP {ip} is not in expected {self.subnet}")
                        desired = self.vms[name].get("reserved_ip", "")
                        if desired and desired != ip:
                            raise LabError(f"{name}: DHCP address {ip} != configured reservation {desired}")
                        ips[name] = ip
                        out(f"  {name:10s} {ip}")
                        break
                    except ValueError:
                        pass
                last_error = result.stderr.strip()[-200:]
                time.sleep(3)
            if name not in ips:
                raise LabError(f"Could not resolve {name} via Tart guest agent ({last_error}).")
        return ips

    def existing_ips(self) -> dict[str, str]:
        if not IPS_FILE.exists():
            return {}
        try:
            return json.loads(IPS_FILE.read_text(encoding="utf-8"))["ips"]
        except (OSError, ValueError, KeyError) as exc:
            raise LabError(f"Invalid state file {IPS_FILE}: {exc}") from exc

    def guard_ips(self, ips: dict[str, str]) -> None:
        previous = self.existing_ips()
        changes = {name: (previous[name], ip) for name, ip in ips.items()
                   if name in previous and previous[name] != ip}
        if changes:
            details = ", ".join(f"{n}: {old} -> {new}" for n, (old, new) in changes.items())
            raise LabError("VM IP DRIFT DETECTED: " + details +
                           ". No kubeadm reset/change attempted. Restore DHCP reservations; "
                           "see docs/networking.md. Never force a new IP into kubeadm blindly.")

    def save_ips(self, ips: dict[str, str]) -> None:
        write_secret(IPS_FILE, json.dumps({
            "cluster": self.name,
            "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "ips": ips}, indent=2) + "\n")

    def ssh_base(self, ip: str, *, interactive: bool = False,
                 password_allowed: bool = False) -> list[str]:
        args = ["ssh", "-o", "StrictHostKeyChecking=accept-new",
                "-o", "ConnectTimeout=8",
                "-o", "ServerAliveInterval=10"]
        if interactive:
            args += ["-tt"]
        elif not password_allowed:
            args += ["-o", "BatchMode=yes"]
        if self.key.exists():
            args += ["-i", str(self.key), "-o", "IdentitiesOnly=yes"]
        args.append(f"{self.ssh_user}@{ip}")
        return args

    def ssh(self, ip: str, command: str, *, stdin: str | None = None,
            timeout: int = 40, check: bool = True) -> subprocess.CompletedProcess[str]:
        return call(self.ssh_base(ip) + [command], input_text=stdin,
                    timeout=timeout, check=check)

    def wait_ssh(self, ips: dict[str, str]) -> None:
        timeout = int(self.cluster["ssh_wait_seconds"])
        for name, ip in ips.items():
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                result = self.ssh(ip, "true", check=False, timeout=12)
                if result.returncode == 0:
                    break
                time.sleep(4)
            else:
                raise LabError(f"Cannot SSH as {self.ssh_user}@{ip}. "
                               "Run `python3 k8sctl.py access` once, or configure keys manually.")
            check = self.ssh(ip, "sudo -n true", check=False)
            if check.returncode:
                raise LabError(f"Passwordless sudo unavailable on {name}. "
                               "Run `python3 k8sctl.py access` (lab-only sudoers), then retry.")
            out(f"SSH and sudo OK: {name} ({ip})")

    def access(self) -> None:
        """Intentional one-time interactive credential bootstrap for isolated lab."""
        if not self.key.exists():
            out(f"==> Generating new SSH key {self.key}")
            self.key.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "",
                            "-f", str(self.key)], check=True)
        pub = self.key.with_suffix(self.key.suffix + ".pub")
        if not pub.exists():
            raise LabError(f"Public key not found: {pub}")
        ips = self.discover_ips()
        self.guard_ips(ips)
        for name, ip in ips.items():
            out(f"==> Set up SSH key on {name} ({ip}); enter the VM password if asked")
            command = "umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys"
            # No remote TTY for this pipe; SSH password auth still prompts via /dev/tty.
            p = subprocess.run(self.ssh_base(ip, password_allowed=True) + [command],
                               input=pub.read_text(), text=True)
            if p.returncode:
                raise LabError(f"Could not install SSH key on {name}")
            # sudo command is visibly interactive and affects this lab VM only.
            rule = f"{self.ssh_user} ALL=(ALL) NOPASSWD: ALL"
            filename = "/etc/sudoers.d/95-k8s-tart-lab"
            inner = f"printf '%s\\n' {shlex.quote(rule)} > {filename} && chmod 440 {filename} && visudo -c -f {filename}"
            out(f"==> Configure lab-only passwordless sudo on {name}; enter VM password if asked")
            subprocess.run(self.ssh_base(ip, interactive=True) +
                           ["sudo sh -c " + shlex.quote(inner)], check=True)
        out("Lab SSH/sudo access prepared. Do not use this lab sudo policy on production hosts.")

    def connectivity(self, ips: dict[str, str]) -> None:
        for name, ip in ips.items():
            self.ssh(ip, "true")
            out(f"SSH reachable: {name} {ip}")
        # This TCP check runs on workers, so success requires guest-to-guest connectivity.
        target = ips[self.cp]
        probe = ("python3 -c " + shlex.quote(
            "import socket; s=socket.socket(); s.settimeout(3); "
            f"s.connect(('{target}', 22)); s.close(); print('VM-to-VM TCP OK')"))
        for name in self.workers:
            result = self.ssh(ips[name], probe)
            out(f"{name} -> {self.cp}: {result.stdout.strip()}")

    def node_file(self, ip: str, path: str) -> bool:
        return self.ssh(ip, f"sudo -n test -f {shlex.quote(path)}", check=False).returncode == 0

    def prepare(self, ips: dict[str, str]) -> None:
        body = PREP.read_text(encoding="utf-8")
        for name, ip in ips.items():
            if self.node_file(ip, "/etc/kubernetes/admin.conf") or self.node_file(ip, "/etc/kubernetes/kubelet.conf"):
                out(f"SKIP {name}: existing kubeadm state detected")
                continue
            out(f"==> Initial guest preparation: {name} (may download APT packages)")
            invocation = (f"sudo -n bash -s -- {shlex.quote(name)} "
                          f"{shlex.quote(self.cluster['kubernetes_minor'])}")
            result = self.ssh(ip, invocation, stdin=body, timeout=1800)
            out(result.stdout[-1500:])

    def validate_api_endpoint(self, ip: str) -> None:
        admin_conf = self.ssh(ip, "sudo -n grep -E '^[[:space:]]*server:' /etc/kubernetes/admin.conf").stdout
        addresses = re.findall(r"https://([^:/\s]+):6443", admin_conf)
        if not addresses:
            raise LabError("Could not determine API endpoint from control-plane admin.conf")
        endpoint = addresses[0]
        try:
            is_ip = ipaddress.ip_address(endpoint).version == 4
        except ValueError:
            is_ip = False
        if is_ip and endpoint != ip:
            raise LabError(f"Kubeadm admin.conf endpoint {endpoint} != current control-plane IP {ip}. "
                           "Refusing automatic repair/re-init; restore original DHCP reservation or follow disaster recovery steps.")

    def sync_kubeconfig(self, cp_ip: str) -> None:
        self.validate_api_endpoint(cp_ip)
        raw = self.ssh(cp_ip, "sudo -n cat /etc/kubernetes/admin.conf", timeout=30).stdout
        if "kind: Config" not in raw:
            raise LabError("Control plane returned an invalid kubeconfig")
        write_secret(KUBECONFIG, raw)
        out(f"Local kubeconfig saved: {KUBECONFIG} (mode 600, excluded from Git)")

    def kctl(self, *arguments: str, input_text: str | None = None,
             timeout: int = 60, check: bool = True) -> subprocess.CompletedProcess[str]:
        if not KUBECONFIG.exists():
            raise LabError("No local kubeconfig. Run `adopt` on the existing cluster first.")
        if not shutil.which("kubectl"):
            raise LabError("Local kubectl unavailable. Run `brew install kubectl`.")
        env = os.environ.copy()
        env["KUBECONFIG"] = str(KUBECONFIG)
        return call(["kubectl", *arguments], input_text=input_text,
                    timeout=timeout, check=check, env=env)

    def bootstrap_control_plane(self, ips: dict[str, str]) -> None:
        cp_ip = ips[self.cp]
        if self.node_file(cp_ip, "/etc/kubernetes/admin.conf"):
            out("SKIP: control plane already initialized; will NOT re-run kubeadm init")
        else:
            out(f"==> kubeadm init: {self.cp} {cp_ip}")
            opts = ["sudo", "-n", "kubeadm", "init",
                    f"--apiserver-advertise-address={cp_ip}",
                    f"--pod-network-cidr={self.cluster['pod_cidr']}",
                    f"--service-cidr={self.cluster['service_cidr']}",
                    "--cri-socket=unix:///run/containerd/containerd.sock"]
            result = self.ssh(cp_ip, shlex.join(opts), timeout=1800)
            out(result.stdout[-3000:])
        self.sync_kubeconfig(cp_ip)
        out("==> Testing Kubernetes API")
        out(self.kctl("get", "nodes", "-o", "wide", timeout=45).stdout)

    def flannel_manifest(self) -> str:
        version = self.cluster["flannel_version"]
        if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", version):
            raise LabError(f"Invalid Flannel version: {version}")
        path = ROOT / "vendor" / f"kube-flannel-{version}.yml"
        if not path.exists():
            url = f"https://github.com/flannel-io/flannel/releases/download/{version}/kube-flannel.yml"
            out(f"==> Downloading pinned Flannel manifest: {url}")
            try:
                with urllib.request.urlopen(url, timeout=60) as response:
                    data = response.read(1_000_000).decode("utf-8")
            except Exception as exc:
                raise LabError(f"Could not download Flannel release manifest: {exc}") from exc
            if "kind: DaemonSet" not in data or "kube-flannel" not in data:
                raise LabError("Downloaded Flannel manifest did not pass sanity check")
            path.write_text(data, encoding="utf-8")
        content = path.read_text(encoding="utf-8")
        default = '"Network": "10.244.0.0/16"'
        if default not in content:
            raise LabError("Unexpected Flannel manifest format; cannot safely patch Pod network")
        return content.replace(default, f'"Network": "{self.cluster["pod_cidr"]}"')

    def apply_cni(self) -> None:
        result = self.kctl("get", "namespace", "kube-flannel", check=False)
        if result.returncode == 0:
            out("SKIP: kube-flannel namespace already exists; existing CNI left unchanged")
            return
        out("==> Installing Flannel CNI")
        manifest = self.flannel_manifest()
        out(self.kctl("apply", "-f", "-", input_text=manifest, timeout=180).stdout)

    def join_workers(self, ips: dict[str, str]) -> None:
        new_workers = [name for name in self.workers
                       if not self.node_file(ips[name], "/etc/kubernetes/kubelet.conf")]
        if not new_workers:
            out("SKIP: all worker nodes already have kubelet join state")
            return
        command = self.ssh(ips[self.cp], "sudo -n kubeadm token create --print-join-command",
                           timeout=30).stdout.strip()
        tokens = shlex.split(command)
        if not tokens or tokens[0] != "kubeadm" or "join" not in tokens:
            raise LabError("Unexpected kubeadm token command; refusing worker join")
        # Do NOT print the bootstrap token. Do not persist it in state/reports.
        for name in new_workers:
            out(f"==> Joining worker {name} ({ips[name]})")
            args = ["sudo", "-n", *tokens,
                    "--cri-socket=unix:///run/containerd/containerd.sock"]
            result = self.ssh(ips[name], shlex.join(args), timeout=900)
            out(result.stdout[-1000:])

    def adopt(self) -> None:
        """Never mutates VM configuration or existing Kubernetes resources."""
        ips = self.discover_ips()
        self.guard_ips(ips)
        self.wait_ssh(ips)
        if not self.node_file(ips[self.cp], "/etc/kubernetes/admin.conf"):
            raise LabError("Control plane is not initialized; run `up` for a new cluster.")
        self.sync_kubeconfig(ips[self.cp])
        out("==> Existing Kubernetes nodes")
        out(self.kctl("get", "nodes", "-o", "wide").stdout)
        self.save_ips(ips)
        out("Adopted existing cluster without rebuilding or changing nodes/networking.")

    def up(self) -> None:
        self.preflight()
        if not shutil.which("kubectl"):
            raise LabError("Install macOS kubectl (`brew install kubectl`) before running `up`.")
        self.create()
        self.start(check_preflight=False)
        ips = self.discover_ips()
        self.guard_ips(ips)
        self.wait_ssh(ips)
        self.connectivity(ips)
        self.prepare(ips)
        self.bootstrap_control_plane(ips)
        self.apply_cni()
        self.join_workers(ips)
        self.save_ips(ips)
        out("==> Waiting for node Ready conditions (up to 5 minutes)")
        self.kctl("wait", "--for=condition=Ready", "nodes", "--all", "--timeout=300s", timeout=330)
        out(self.kctl("get", "nodes", "-o", "wide").stdout)
        out("UP completed. Next: `python3 k8sctl.py test`.")

    def stop(self) -> None:
        for name in [*self.workers, self.cp]:
            info = self.vm_info(name)
            if info and info.get("Running"):
                out(f"==> Gracefully stopping {name}")
                call(["tart", "stop", name], timeout=90)
            else:
                out(f"SKIP {name}: absent or already stopped")

    def status(self) -> None:
        out(f"Cluster: {self.name}\nVM network: {self.subnet}")
        old_ips = self.existing_ips()
        for name in self.vms:
            info = self.vm_info(name)
            if info is None:
                out(f"  {name}: ABSENT")
                continue
            status = "running" if info.get("Running") else "stopped"
            ip = "-"
            if info.get("Running"):
                p = call(["tart", "ip", "--resolver=agent", name], check=False, timeout=8)
                if p.returncode == 0 and p.stdout.strip():
                    ip = p.stdout.strip().splitlines()[-1].strip()
            drift = "  !!! IP DRIFT" if old_ips.get(name) and old_ips[name] != ip and ip != "-" else ""
            out(f"  {name:10s} {status:8s} {ip}{drift}")
        if KUBECONFIG.exists() and shutil.which("kubectl"):
            p = self.kctl("get", "nodes", "-o", "wide", check=False, timeout=12)
            out("\nKubernetes nodes:\n" + (p.stdout.strip() or p.stderr.strip()))
            p = self.kctl("get", "pods", "-A", "--field-selector=status.phase!=Running",
                          check=False, timeout=12)
            out("\nNon-running Kubernetes Pods (may include completed Jobs):\n" +
                (p.stdout.strip() or p.stderr.strip()))
        else:
            out("No local kubeconfig/kubectl; run `adopt` once after setting up access.")

    def doctor(self) -> None:
        self.preflight(strict=False)
        self.status()
        out("\n==> Diagnostics (read-only)")
        ips = {}
        for name in self.vms:
            info = self.vm_info(name)
            if not info or not info.get("Running"):
                continue
            p = call(["tart", "ip", "--resolver=agent", name], check=False, timeout=10)
            if p.returncode == 0 and p.stdout.strip():
                ips[name] = p.stdout.strip().splitlines()[-1]
        for name, ip in ips.items():
            out(f"\n--- {name}: {ip} ---")
            script = ("hostname; uname -m; ip -4 -br addr; ip -4 route; "
                      "systemctl is-active containerd || true; "
                      "systemctl is-active kubelet || true; "
                      "sudo -n sysctl -n net.ipv4.ip_forward || true; "
                      "sudo -n swapon --show || true; "
                      "sudo -n ip link show flannel.1 2>/dev/null || true")
            result = self.ssh(ip, script, check=False, timeout=20)
            out((result.stdout or result.stderr).strip()[-2500:])
        if self.cp in ips:
            for worker in self.workers:
                if worker not in ips:
                    continue
                probe = "python3 -c " + shlex.quote(
                    f"import socket; socket.create_connection(('{ips[self.cp]}', 6443), 4).close(); print('API TCP reachable')")
                p = self.ssh(ips[worker], probe, check=False)
                out(f"{worker} -> {self.cp}:6443: " +
                    (p.stdout.strip() if p.returncode == 0 else "FAILED " + p.stderr.strip()[-300:]))
        if KUBECONFIG.exists():
            for args in [("get", "pods", "-n", "kube-flannel", "-o", "wide"),
                         ("get", "pods", "-n", "kube-system", "-o", "wide")]:
                p = self.kctl(*args, check=False, timeout=20)
                out("kubectl " + " ".join(args) + "\n" + (p.stdout or p.stderr).strip())

    def diagnose(self) -> None:
        timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        directory = REPORTS / timestamp
        directory.mkdir(mode=0o700)
        out(f"==> Collecting read-only diagnosis in {directory}")
        datasets: list[tuple[str, list[str], int]] = [
            ("mac-tart-list.txt", ["tart", "list"], 30),
            ("mac-socket-vmnet-processes.txt", ["pgrep", "-fl", "socket_vmnet"], 20),
        ]
        for name, cmd, timeout in datasets:
            res = call(cmd, check=False, timeout=timeout)
            write_secret(directory / name, res.stdout + "\n" + res.stderr)
        for name in self.vms:
            info = self.vm_info(name)
            if not info or not info.get("Running"):
                continue
            addr = call(["tart", "ip", "--resolver=agent", name], check=False)
            if addr.returncode or not addr.stdout.strip():
                continue
            ip = addr.stdout.strip().splitlines()[-1]
            diagnostics = """set +e
hostname; date -Is; uname -a; ip -br addr; ip route
systemctl status containerd --no-pager -l
systemctl status kubelet --no-pager -l
sudo -n journalctl -u kubelet -n 120 --no-pager
sudo -n journalctl -u containerd -n 80 --no-pager
sudo -n crictl --runtime-endpoint unix:///run/containerd/containerd.sock ps -a
sudo -n sysctl net.ipv4.ip_forward net.bridge.bridge-nf-call-iptables
sudo -n swapon --show
sudo -n ip -d link show flannel.1
sudo -n ss -lntup
"""
            p = self.ssh(ip, "bash -s", stdin=diagnostics, check=False, timeout=90)
            write_secret(directory / f"guest-{name}.txt", p.stdout + "\n" + p.stderr)
        if KUBECONFIG.exists():
            commands = [
                ("k8s-nodes.txt", ["get", "nodes", "-o", "wide"]),
                ("k8s-all-pods.txt", ["get", "pods", "-A", "-o", "wide"]),
                ("k8s-events.txt", ["get", "events", "-A", "--sort-by=.lastTimestamp"]),
                ("k8s-flannel.txt", ["get", "pods", "-n", "kube-flannel", "-o", "wide"]),
                ("k8s-system.txt", ["get", "pods", "-n", "kube-system", "-o", "wide"]),
            ]
            for name, args in commands:
                p = self.kctl(*args, check=False, timeout=40)
                write_secret(directory / name, p.stdout + "\n" + p.stderr)
            p = self.kctl("logs", "-n", "kube-flannel", "-l", "app=flannel",
                          "--all-containers=true", "--tail=120", "--max-log-requests=10",
                          check=False, timeout=45)
            write_secret(directory / "flannel-logs.txt", p.stdout + "\n" + p.stderr)
        out("Diagnostic bundle saved. Treat logs as potentially sensitive; review before sharing.")

    def test(self, keep: bool = False) -> None:
        self.kctl("get", "nodes", timeout=20)
        namespace = "k8s-tart-smoke"
        existing = self.kctl("get", "ns", namespace, check=False)
        if existing.returncode == 0:
            raise LabError(f"Namespace {namespace} already exists. Remove it explicitly; not overwriting it.")
        out("==> Creating disposable smoke test namespace")
        self.kctl("create", "namespace", namespace)
        try:
            for index, name in enumerate(self.workers[:2], start=1):
                pod_name = f"net-{index}"
                overrides = json.dumps({"spec": {"nodeSelector": {
                    "kubernetes.io/hostname": name}}})
                self.kctl("-n", namespace, "run", pod_name, "--image=busybox:1.36",
                          "--restart=Never", f"--overrides={overrides}", "--command", "--", "sleep", "600")
            self.kctl("-n", namespace, "create", "deployment", "web", "--image=nginx:stable")
            self.kctl("-n", namespace, "expose", "deployment", "web", "--port=80", "--target-port=80")
            self.kctl("-n", namespace, "wait", "--for=condition=Ready", "pod/net-1", "pod/net-2",
                      "--timeout=180s", timeout=205)
            self.kctl("-n", namespace, "rollout", "status", "deployment/web",
                      "--timeout=180s", timeout=205)
            other = self.kctl("-n", namespace, "get", "pod", "net-2", "-o", "jsonpath={.status.podIP}").stdout.strip()
            if not other:
                raise LabError("No IP for second smoke-test pod")
            p = self.kctl("-n", namespace, "exec", "net-1", "--", "ping", "-c", "3", "-W", "4", other,
                          timeout=25)
            out("Cross-worker Pod ping OK:\n" + p.stdout.strip())
            p = self.kctl("-n", namespace, "exec", "net-1", "--", "nslookup",
                          "kubernetes.default.svc.cluster.local", timeout=25)
            out("Cluster DNS OK:\n" + p.stdout.strip())
            p = self.kctl("-n", namespace, "exec", "net-1", "--", "wget", "-q", "-O", "-",
                          "-T", "10", "http://web", timeout=30)
            if "Welcome to nginx" not in p.stdout and "nginx" not in p.stdout.lower():
                raise LabError("NGINX Service response did not resemble the welcome page")
            out("ClusterIP service -> NGINX OK")
            out("SMOKE TEST PASSED: cross-node Pod network, DNS, and Service")
        finally:
            if not keep:
                p = self.kctl("delete", "namespace", namespace, "--wait=false",
                              check=False, timeout=35)
                out("Smoke test namespace delete requested: " + (p.stdout or p.stderr).strip())
            else:
                out(f"Smoke test namespace kept: {namespace} (manual cleanup: kubectl delete ns {namespace})")

    def monitor(self, interval: int, count: int) -> None:
        index = 0
        try:
            while count == 0 or index < count:
                out("\n" + "=" * 55 + " " + dt.datetime.now().isoformat(timespec="seconds"))
                self.status()
                index += 1
                if count == 0 or index < count:
                    time.sleep(interval)
        except KeyboardInterrupt:
            out("Stopped monitoring")

    def confirmation(self, yes: bool, phrase: str | None, action: str) -> None:
        if not yes or phrase != self.name:
            raise LabError(f"{action} is DESTRUCTIVE. Pass --yes --confirm {self.name} exactly.")

    def reset_k8s(self, yes: bool, phrase: str | None) -> None:
        self.confirmation(yes, phrase, "reset-k8s")
        ips = self.discover_ips()
        self.guard_ips(ips)
        self.wait_ssh(ips)
        # Reset workers first, then the API/etcd control plane.
        for name in [*self.workers, self.cp]:
            out(f"==> RESET KUBERNETES on {name} (does NOT delete the VM)")
            statement = """set -e
kubeadm reset -f
rm -rf /etc/cni/net.d /var/lib/cni
ip link delete cni0 2>/dev/null || true
ip link delete flannel.1 2>/dev/null || true
"""
            p = self.ssh(ips[name], "sudo -n bash -s", stdin=statement, timeout=180)
            out(p.stdout[-800:])
        if KUBECONFIG.exists():
            KUBECONFIG.unlink()
        out("Kubernetes reset requested. VM OS, containerd, apt packages and shim are retained.")

    def destroy(self, yes: bool, phrase: str | None) -> None:
        self.confirmation(yes, phrase, "destroy")
        self.stop()
        for name in self.vms:
            if self.vm_info(name) is None:
                continue
            out(f"==> Deleting Tart VM {name}")
            call(["tart", "delete", name], timeout=180)
        if KUBECONFIG.exists():
            KUBECONFIG.unlink()
        if IPS_FILE.exists():
            IPS_FILE.unlink()
        out("VMs deleted. Existing socket_vmnet daemon, softnet shim, logs and reports were NOT touched.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=CONFIG_FILE,
                        help="TOML configuration (default: config/cluster.toml)")
    commands = parser.add_subparsers(dest="command", required=True)
    for command, help_text in [
        ("preflight", "Read-only host/shim/socket checks"),
        ("access", "Interactive one-time SSH key and lab sudo setup"),
        ("adopt", "Inspect and register existing working Kubernetes cluster (no mutation)"),
        ("create", "Create only missing Tart VMs; never change existing ones"),
        ("start", "Start existing VMs using the shim; block on IP drift"),
        ("up", "Idempotent-ish fresh provision/reconcile; preserve existing kubeadm state"),
        ("stop", "Stop Tart VMs without deleting Kubernetes data"),
        ("status", "Quick VM and cluster status"),
        ("doctor", "Read-only VM/network/Kubernetes diagnostics"),
        ("diagnose", "Save detailed read-only diagnostic report"),
        ("test", "Run disposable cross-node networking/DNS/Service smoke tests"),
        ("monitor", "Poll cluster status continuously"),
        ("reset-k8s", "DESTRUCTIVE: kubeadm reset on each guest; preserve VMs"),
        ("destroy", "DESTRUCTIVE: remove all configured Tart VMs; preserve shim"),
    ]:
        command_parser = commands.add_parser(command, help=help_text)
        if command == "test":
            command_parser.add_argument("--keep", action="store_true", help="Keep smoke test namespace")
        if command == "monitor":
            command_parser.add_argument("--interval", type=int, default=30, help="Seconds between polls")
            command_parser.add_argument("--count", type=int, default=0, help="0=forever")
        if command in ("reset-k8s", "destroy"):
            command_parser.add_argument("--yes", action="store_true")
            command_parser.add_argument("--confirm", help="Must equal the cluster name in config")
    args = parser.parse_args()
    try:
        lab = Lab(args.config)
        if args.command == "preflight": lab.preflight()
        elif args.command == "access": lab.access()
        elif args.command == "adopt": lab.adopt()
        elif args.command == "create": lab.create()
        elif args.command == "start": lab.start()
        elif args.command == "up": lab.up()
        elif args.command == "stop": lab.stop()
        elif args.command == "status": lab.status()
        elif args.command == "doctor": lab.doctor()
        elif args.command == "diagnose": lab.diagnose()
        elif args.command == "test": lab.test(keep=args.keep)
        elif args.command == "monitor": lab.monitor(args.interval, args.count)
        elif args.command == "reset-k8s": lab.reset_k8s(args.yes, args.confirm)
        elif args.command == "destroy": lab.destroy(args.yes, args.confirm)
        return 0
    except (LabError, KeyError, ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
