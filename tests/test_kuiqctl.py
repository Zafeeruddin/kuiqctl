import importlib.machinery
import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("kuiqctl", str(ROOT / "kuiqctl"))
spec = importlib.util.spec_from_loader(loader.name, loader)
kuiqctl = importlib.util.module_from_spec(spec)
loader.exec_module(kuiqctl)


class ConfigTests(unittest.TestCase):
    def test_home_and_office_networks_are_valid(self):
        config = kuiqctl.defaults()
        config["endpoint"] = "server.local"
        kuiqctl.validate_config(config)

    def test_rejects_cluster_network_overlapping_lan(self):
        config = kuiqctl.defaults()
        config["endpoint"] = "server.local"
        config["pod_cidr"] = "192.168.1.0/24"
        with self.assertRaisesRegex(kuiqctl.KuiqctlError, "overlaps"):
            kuiqctl.validate_config(config)

    def test_reuses_docker_containerd_io_instead_of_conflicting_package(self):
        with mock.patch.object(kuiqctl.shutil, "which", return_value="/usr/bin/containerd"):
            self.assertNotIn("containerd", kuiqctl.prerequisite_packages())

    def test_installs_containerd_when_no_runtime_exists(self):
        with mock.patch.object(kuiqctl.shutil, "which", return_value=None):
            self.assertIn("containerd", kuiqctl.prerequisite_packages())

    def test_rejects_overlapping_pod_and_service_networks(self):
        config = kuiqctl.defaults()
        config["endpoint"] = "server.local"
        config["service_cidr"] = "10.244.1.0/24"
        with self.assertRaisesRegex(kuiqctl.KuiqctlError, "overlaps"):
            kuiqctl.validate_config(config)

    def test_rejects_stable_node_ip_inside_a_cluster_network(self):
        config = kuiqctl.defaults()
        config["endpoint"] = "server.local"
        config["stable_node_ip"] = "10.244.10.5"
        with self.assertRaisesRegex(kuiqctl.KuiqctlError, "overlaps"):
            kuiqctl.validate_config(config)


class KubeconfigTests(unittest.TestCase):
    def test_rewrites_endpoint_and_names(self):
        original = "server: https://10.255.255.1:6443\nname: kubernetes\ncurrent-context: kubernetes-admin\n"
        result = kuiqctl.rewrite_kubeconfig(original, "node.local", "demo")
        self.assertIn("https://node.local:6443", result)
        self.assertNotIn("kubernetes-admin", result)
        self.assertEqual(result.count("demo"), 2)


class KubeadmConfigTests(unittest.TestCase):
    def test_generated_config_uses_stable_internal_address_and_roaming_san(self):
        config = kuiqctl.defaults()
        config["endpoint"] = "server.local"
        with tempfile.TemporaryDirectory() as directory:
            original = kuiqctl.KUBEADM_CONFIG
            try:
                kuiqctl.KUBEADM_CONFIG = pathlib.Path(directory) / "kubeadm.yaml"
                kuiqctl.write_kubeadm_config(config)
                rendered = kuiqctl.KUBEADM_CONFIG.read_text()
            finally:
                kuiqctl.KUBEADM_CONFIG = original
        self.assertIn('controlPlaneEndpoint: "10.255.255.1:6443"', rendered)
        self.assertIn('advertiseAddress: "10.255.255.1"', rendered)
        self.assertIn('    - "server.local"', rendered)
        self.assertIn("taints: []", rendered)


if __name__ == "__main__":
    unittest.main()
