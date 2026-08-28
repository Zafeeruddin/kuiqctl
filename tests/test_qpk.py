import importlib.machinery
import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("qpk", str(ROOT / "qpk"))
spec = importlib.util.spec_from_loader(loader.name, loader)
qpk = importlib.util.module_from_spec(spec)
loader.exec_module(qpk)


class ConfigTests(unittest.TestCase):
    def test_home_and_office_networks_are_valid(self):
        config = qpk.defaults()
        config["endpoint"] = "server.local"
        qpk.validate_config(config)

    def test_rejects_cluster_network_overlapping_lan(self):
        config = qpk.defaults()
        config["endpoint"] = "server.local"
        config["pod_cidr"] = "192.168.1.0/24"
        with self.assertRaisesRegex(qpk.QPKError, "overlaps"):
            qpk.validate_config(config)

    def test_rejects_overlapping_pod_and_service_networks(self):
        config = qpk.defaults()
        config["endpoint"] = "server.local"
        config["service_cidr"] = "10.244.1.0/24"
        with self.assertRaisesRegex(qpk.QPKError, "overlaps"):
            qpk.validate_config(config)

    def test_rejects_stable_node_ip_inside_a_cluster_network(self):
        config = qpk.defaults()
        config["endpoint"] = "server.local"
        config["stable_node_ip"] = "10.244.10.5"
        with self.assertRaisesRegex(qpk.QPKError, "overlaps"):
            qpk.validate_config(config)


class KubeconfigTests(unittest.TestCase):
    def test_rewrites_endpoint_and_names(self):
        original = "server: https://10.255.255.1:6443\nname: kubernetes\ncurrent-context: kubernetes-admin\n"
        result = qpk.rewrite_kubeconfig(original, "node.local", "demo")
        self.assertIn("https://node.local:6443", result)
        self.assertNotIn("kubernetes-admin", result)
        self.assertEqual(result.count("demo"), 2)


class KubeadmConfigTests(unittest.TestCase):
    def test_generated_config_uses_stable_internal_address_and_roaming_san(self):
        config = qpk.defaults()
        config["endpoint"] = "server.local"
        with tempfile.TemporaryDirectory() as directory:
            original = qpk.KUBEADM_CONFIG
            try:
                qpk.KUBEADM_CONFIG = pathlib.Path(directory) / "kubeadm.yaml"
                qpk.write_kubeadm_config(config)
                rendered = qpk.KUBEADM_CONFIG.read_text()
            finally:
                qpk.KUBEADM_CONFIG = original
        self.assertIn('controlPlaneEndpoint: "10.255.255.1:6443"', rendered)
        self.assertIn('advertiseAddress: "10.255.255.1"', rendered)
        self.assertIn('    - "server.local"', rendered)
        self.assertIn("taints: []", rendered)


if __name__ == "__main__":
    unittest.main()
