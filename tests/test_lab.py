import ipaddress
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from k8sctl import Lab, LabError, client_kubeconfig_path, write_secret


class LabSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lab = Lab()

    def test_network_is_expected(self):
        self.assertEqual(self.lab.subnet, ipaddress.ip_network('192.168.105.0/24'))
        self.assertEqual(self.lab.cp, 'k8s-cp')
        self.assertEqual(set(self.lab.workers), {'k8s-w1', 'k8s-w2'})
        self.assertEqual(self.lab.cli_aliases, ['ttk'])

    def test_shim_precedes_normal_path(self):
        self.assertEqual(self.lab.net_env()['PATH'].split(':')[0],
                         '/opt/tart-vmnet-shim/bin')
        self.assertEqual(self.lab.net_env()['SOCKET_VMNET_PATH'],
                         '/var/run/socket_vmnet')

    def test_unsupported_network_mode_is_rejected(self):
        with self.assertRaisesRegex(LabError, "network.mode must be 'softnet'"):
            self.lab_from_replacement('mode = "softnet"', 'mode = "bridged"')

    def test_relative_network_paths_are_rejected(self):
        for key, value in [('softnet_bin', 'bin/softnet'),
                           ('socket_path', 'run/socket_vmnet')]:
            with self.subTest(key=key):
                with self.assertRaisesRegex(LabError, f'network.{key} must be an absolute path'):
                    self.lab_from_replacement(
                        f'{key} = "/opt/tart-vmnet-shim/bin/softnet"' if key == 'softnet_bin'
                        else f'{key} = "/var/run/socket_vmnet"',
                        f'{key} = "{value}"')

    def test_explicit_client_kubeconfig_path_wins(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'client-config'
            with patch.dict('os.environ', {'KUBECONFIG': '/ignored/config'}):
                self.assertEqual(client_kubeconfig_path(path), path.resolve())

    def test_kubeconfig_environment_uses_first_path(self):
        with patch.dict('os.environ', {'KUBECONFIG': '/first/config:/second/config'}):
            self.assertEqual(client_kubeconfig_path(), Path('/first/config'))

    def test_ip_drift_fails_closed(self):
        with patch.object(self.lab, 'existing_ips', return_value={'k8s-cp': '192.168.105.4'}):
            with self.assertRaisesRegex(LabError, 'IP DRIFT'):
                self.lab.guard_ips({'k8s-cp': '192.168.105.10'})

    def test_matching_ip_is_allowed(self):
        with patch.object(self.lab, 'existing_ips', return_value={'k8s-cp': '192.168.105.4'}):
            self.lab.guard_ips({'k8s-cp': '192.168.105.4'})

    def test_access_issues_distinguish_ssh_and_sudo(self):
        ips = {'k8s-cp': '192.168.105.4', 'k8s-w1': '192.168.105.2'}
        failed = MagicMock(returncode=255)
        okay = MagicMock(returncode=0)
        sudo_failed = MagicMock(returncode=1)
        with patch.object(self.lab, 'ssh', side_effect=[failed, okay, sudo_failed]):
            self.assertEqual(self.lab.access_issues(ips), {
                'k8s-cp': 'SSH key login unavailable',
                'k8s-w1': 'passwordless sudo unavailable',
            })

    def test_ssh_rejects_unknown_node(self):
        with self.assertRaisesRegex(LabError, 'Unknown node'):
            self.lab.connect_node('not-a-node')

    def test_ssh_rejects_stopped_node(self):
        with patch.object(self.lab, 'vm_info', return_value={'Running': False}), \
             self.assertRaisesRegex(LabError, 'is stopped'):
            self.lab.connect_node('k8s-cp')

    def test_ssh_opens_interactive_session_with_ip_guard(self):
        completed = subprocess.CompletedProcess([], 0)
        with patch.object(self.lab, 'vm_info', return_value={'Running': True}), \
             patch.object(self.lab, 'discover_node_ip', return_value='192.168.105.11'), \
             patch.object(self.lab, 'guard_ips') as guard, \
             patch('k8sctl.subprocess.run', return_value=completed) as invoke:
            self.lab.connect_node('k8s-cp')
        guard.assert_called_once_with({'k8s-cp': '192.168.105.11'})
        ssh_args = invoke.call_args.args[0]
        self.assertIn('-tt', ssh_args)
        self.assertEqual(ssh_args[-1], 'admin@192.168.105.11')

    def test_ssh_runs_remote_command_without_tty(self):
        completed = subprocess.CompletedProcess([], 0)
        with patch.object(self.lab, 'vm_info', return_value={'Running': True}), \
             patch.object(self.lab, 'discover_node_ip', return_value='192.168.105.13'), \
             patch.object(self.lab, 'guard_ips'), \
             patch('k8sctl.subprocess.run', return_value=completed) as invoke:
            self.lab.connect_node('k8s-w1', 'hostname && uptime')
        ssh_args = invoke.call_args.args[0]
        self.assertNotIn('-tt', ssh_args)
        self.assertIn('BatchMode=yes', ssh_args)
        self.assertEqual(ssh_args[-2:], ['admin@192.168.105.13', 'hostname && uptime'])

    def test_deletion_requires_exact_confirmation(self):
        for yes, phrase in [(False, 'tart-kubeadm-lab'), (True, 'wrong'), (True, None)]:
            with self.assertRaises(LabError):
                self.lab.confirmation(yes, phrase, 'destroy')
        self.lab.confirmation(True, 'tart-kubeadm-lab', 'destroy')

    def test_bad_cidr_overlaps_are_rejected(self):
        original = (Path(__file__).resolve().parents[1] / 'config' / 'cluster.toml').read_text()
        replacement = original.replace('pod_cidr = "10.244.0.0/16"',
                                       'pod_cidr = "192.168.105.0/24"')
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write(replacement)
            filename = f.name
        try:
            with self.assertRaisesRegex(LabError, 'overlap'):
                Lab(Path(filename))
        finally:
            Path(filename).unlink()

    def lab_from_replacement(self, old, new):
        original = (Path(__file__).resolve().parents[1] / 'config' / 'cluster.toml').read_text()
        replacement = original.replace(old, new)
        self.assertNotEqual(original, replacement)
        temporary = tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False)
        try:
            temporary.write(replacement)
            temporary.close()
            return Lab(Path(temporary.name))
        finally:
            Path(temporary.name).unlink()

    def test_multiple_control_planes_are_rejected(self):
        with self.assertRaisesRegex(LabError, 'exactly one control-plane'):
            self.lab_from_replacement('role = "worker"', 'role = "control-plane"')

    def test_unknown_vm_role_is_rejected(self):
        with self.assertRaisesRegex(LabError, 'Invalid VM role'):
            self.lab_from_replacement('role = "worker"', 'role = "database"')

    def test_unsafe_cli_alias_is_rejected(self):
        with self.assertRaisesRegex(LabError, 'Unsafe CLI alias'):
            self.lab_from_replacement('cli_aliases = ["ttk"]',
                                      'cli_aliases = ["../../unsafe"]')

    def test_duplicate_reserved_ips_are_rejected(self):
        replacement = 'reserved_ip = "192.168.105.20"'
        original = (Path(__file__).resolve().parents[1] / 'config' / 'cluster.toml').read_text()
        configured = original.replace('reserved_ip = ""', replacement)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write(configured)
            filename = f.name
        try:
            with self.assertRaisesRegex(LabError, 'Duplicate reserved IP'):
                Lab(Path(filename))
        finally:
            Path(filename).unlink()

    def test_create_skips_preexisting_vms_without_modifying_them(self):
        with patch.object(self.lab, 'preflight') as preflight, \
             patch.object(self.lab, 'vm_info', return_value={'Running': True}), \
             patch('k8sctl.call') as invoke:
            self.lab.create()
            preflight.assert_called_once_with(show_next_steps=False)
            invoke.assert_not_called()

    def test_control_plane_initialized_is_never_reinitialized(self):
        ips = {'k8s-cp': '192.168.105.4', 'k8s-w1': '192.168.105.2',
               'k8s-w2': '192.168.105.3'}
        response = MagicMock(stdout='NAME k8s-cp Ready')
        with patch.object(self.lab, 'node_file', return_value=True), \
             patch.object(self.lab, 'sync_kubeconfig'), \
             patch.object(self.lab, 'kctl', return_value=response), \
             patch.object(self.lab, 'ssh') as remote:
            initialized = self.lab.bootstrap_control_plane(ips)
            self.assertFalse(initialized)
            remote.assert_not_called()

    def test_adopt_is_read_only_to_cluster(self):
        ips = {'k8s-cp': '192.168.105.4', 'k8s-w1': '192.168.105.2',
               'k8s-w2': '192.168.105.3'}
        response = MagicMock(stdout='all nodes Ready')
        with patch.object(self.lab, 'discover_ips', return_value=ips), \
             patch.object(self.lab, 'guard_ips'), \
             patch.object(self.lab, 'wait_ssh'), \
             patch.object(self.lab, 'node_file', return_value=True), \
             patch.object(self.lab, 'sync_kubeconfig'), \
             patch.object(self.lab, 'kctl', return_value=response), \
             patch.object(self.lab, 'save_ips') as save, \
             patch.object(self.lab, 'prepare') as prepare, \
             patch.object(self.lab, 'bootstrap_control_plane') as init:
            self.lab.adopt()
            save.assert_called_once_with(ips)
            prepare.assert_not_called()
            init.assert_not_called()

    def test_secrets_mode_0600(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / 'kubeconfig'
            write_secret(dest, 'example')
            self.assertEqual(dest.stat().st_mode & 0o777, 0o600)

    def test_manifest_version_guard(self):
        old_version = self.lab.cluster['flannel_version']
        try:
            self.lab.cluster['flannel_version'] = '../../unsafe'
            with self.assertRaisesRegex(LabError, 'Invalid Flannel version'):
                self.lab.flannel_manifest()
        finally:
            self.lab.cluster['flannel_version'] = old_version

    def test_cached_manifest_hash_mismatch_is_rejected(self):
        old_hash = self.lab.cluster['flannel_sha256']
        try:
            self.lab.cluster['flannel_sha256'] = '0' * 64
            with tempfile.TemporaryDirectory() as folder:
                vendor = Path(folder) / 'vendor'
                vendor.mkdir()
                (vendor / f"kube-flannel-{self.lab.cluster['flannel_version']}.yml").write_text(
                    'kind: DaemonSet\nname: kube-flannel\n', encoding='utf-8')
                with patch('k8sctl.ROOT', Path(folder)):
                    with self.assertRaisesRegex(LabError, 'SHA-256 mismatch'):
                        self.lab.flannel_manifest()
        finally:
            self.lab.cluster['flannel_sha256'] = old_hash

    def test_remote_image_tag_without_digest_is_rejected(self):
        with self.assertRaisesRegex(LabError, 'must be pinned'):
            self.lab_from_replacement(
                'ubuntu_image = "ghcr.io/cirruslabs/ubuntu@sha256:'
                '3acc11bebedcbcb813fb17dd0a4671a8c2e6baed537f3caa7922e170ed8a04ed"',
                'ubuntu_image = "ghcr.io/cirruslabs/ubuntu:24.04"')

    def test_invalid_kubernetes_key_hash_is_rejected(self):
        with self.assertRaisesRegex(LabError, 'kubernetes_release_key_sha256'):
            self.lab_from_replacement(
                'kubernetes_release_key_sha256 = '
                '"7627818cf7bae52f9008c93e8b1f961f53dea11d40891778de216fb1b43be54d"',
                'kubernetes_release_key_sha256 = "unsafe"')

    def test_existing_flannel_is_preserved(self):
        daemonsets = {"items": [{"metadata": {
            "namespace": "kube-flannel", "name": "kube-flannel-ds"}}]}
        response = MagicMock(stdout=json.dumps(daemonsets), returncode=0)
        with patch.object(self.lab, 'validate_cluster_networks'), \
             patch.object(self.lab, 'kctl', return_value=response) as kctl, \
             patch.object(self.lab, 'flannel_manifest') as manifest:
            self.lab.apply_cni(newly_initialized=False)
            manifest.assert_not_called()
            self.assertEqual(kctl.call_count, 1)

    def test_other_cni_blocks_flannel_install(self):
        daemonsets = {"items": [{
            "metadata": {"namespace": "kube-system", "name": "cilium"},
            "spec": {"template": {"spec": {"containers": [
                {"image": "quay.io/cilium/cilium:v1"}]}}},
        }]}
        ds_response = MagicMock(stdout=json.dumps(daemonsets), returncode=0)
        missing_namespace = subprocess.CompletedProcess([], 1, '', 'not found')
        with patch.object(self.lab, 'validate_cluster_networks'), \
             patch.object(self.lab, 'kctl', side_effect=[ds_response, missing_namespace]), \
             patch.object(self.lab, 'flannel_manifest') as manifest:
            with self.assertRaisesRegex(LabError, 'non-Flannel CNI'):
                self.lab.apply_cni(newly_initialized=False)
            manifest.assert_not_called()

    def test_cluster_pod_cidr_mismatch_is_rejected(self):
        nodes = MagicMock(stdout=json.dumps({"items": [{
            "metadata": {"name": "worker"},
            "spec": {"podCIDR": "10.245.1.0/24"},
        }]}))
        with patch.object(self.lab, 'kctl', return_value=nodes):
            with self.assertRaisesRegex(LabError, 'outside configured cluster.pod_cidr'):
                self.lab.validate_cluster_networks()


if __name__ == '__main__':
    unittest.main()
