import ipaddress
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from k8sctl import Lab, LabError, write_secret


class LabSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lab = Lab()

    def test_network_is_expected(self):
        self.assertEqual(self.lab.subnet, ipaddress.ip_network('192.168.105.0/24'))
        self.assertEqual(self.lab.cp, 'k8s-cp')
        self.assertEqual(set(self.lab.workers), {'k8s-w1', 'k8s-w2'})

    def test_shim_precedes_normal_path(self):
        self.assertEqual(self.lab.net_env()['PATH'].split(':')[0],
                         '/opt/tart-vmnet-shim/bin')
        self.assertEqual(self.lab.net_env()['SOCKET_VMNET_PATH'],
                         '/private/var/run/lima/socket_vmnet.shared')

    def test_ip_drift_fails_closed(self):
        with patch.object(self.lab, 'existing_ips', return_value={'k8s-cp': '192.168.105.4'}):
            with self.assertRaisesRegex(LabError, 'IP DRIFT'):
                self.lab.guard_ips({'k8s-cp': '192.168.105.10'})

    def test_matching_ip_is_allowed(self):
        with patch.object(self.lab, 'existing_ips', return_value={'k8s-cp': '192.168.105.4'}):
            self.lab.guard_ips({'k8s-cp': '192.168.105.4'})

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

    def test_create_skips_preexisting_vms_without_modifying_them(self):
        with patch.object(self.lab, 'preflight'), \
             patch.object(self.lab, 'vm_info', return_value={'Running': True}), \
             patch('k8sctl.call') as invoke:
            self.lab.create()
            invoke.assert_not_called()

    def test_control_plane_initialized_is_never_reinitialized(self):
        ips = {'k8s-cp': '192.168.105.4', 'k8s-w1': '192.168.105.2',
               'k8s-w2': '192.168.105.3'}
        response = MagicMock(stdout='NAME k8s-cp Ready')
        with patch.object(self.lab, 'node_file', return_value=True), \
             patch.object(self.lab, 'sync_kubeconfig'), \
             patch.object(self.lab, 'kctl', return_value=response), \
             patch.object(self.lab, 'ssh') as remote:
            self.lab.bootstrap_control_plane(ips)
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


if __name__ == '__main__':
    unittest.main()
