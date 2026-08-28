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

    def test_create_preflight_points_stale_ports_to_recreate(self):
        with (
            mock.patch.object(kuiqctl, "occupied_control_plane_ports", return_value=[10257, 10259]),
            mock.patch.object(kuiqctl, "cluster_present", return_value=False),
            mock.patch.object(kuiqctl, "legacy_k3s_present", return_value=False),
        ):
            with self.assertRaisesRegex(
                kuiqctl.KuiqctlError,
                r"10257, 10259.*sudo kuiqctl recreate --yes",
            ):
                kuiqctl.clean_host_preflight()

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
                with mock.patch.object(kuiqctl, "installed_kubernetes_version", return_value="v1.37.4"):
                    kuiqctl.write_kubeadm_config(config)
                rendered = kuiqctl.KUBEADM_CONFIG.read_text()
            finally:
                kuiqctl.KUBEADM_CONFIG = original
        self.assertIn('controlPlaneEndpoint: "10.255.255.1:6443"', rendered)
        self.assertIn('advertiseAddress: "10.255.255.1"', rendered)
        self.assertIn('    - "server.local"', rendered)
        self.assertIn("taints: []", rendered)
        self.assertIn('kubernetesVersion: "v1.37.4"', rendered)
        self.assertIn('imageRepository: "registry.k8s.io"', rendered)


class ArtifactPreflightTests(unittest.TestCase):
    def test_network_failure_is_actionable_and_preserves_cluster(self):
        error = kuiqctl.artifact_failure(
            "pulling Kubernetes images",
            "dial udp 8.8.8.8:53: connect: network is unreachable",
        )
        self.assertIn("no usable route", str(error))
        self.assertIn("No existing cluster state was reset", str(error))

    def test_missing_default_route_stops_network_preflight(self):
        config = kuiqctl.defaults()
        config["endpoint"] = "server.local"
        with mock.patch.object(kuiqctl, "primary_ip", return_value=""):
            with self.assertRaisesRegex(kuiqctl.KuiqctlError, "no usable default IPv4 route"):
                kuiqctl.resolve_required_hosts(config)

    def test_recreate_prepares_artifacts_before_reset(self):
        config = kuiqctl.defaults()
        config["endpoint"] = "server.local"
        with (
            mock.patch.object(kuiqctl, "require_root"),
            mock.patch.object(kuiqctl, "lifecycle_lock", return_value=kuiqctl.contextlib.nullcontext()),
            mock.patch.object(
                kuiqctl,
                "prepare_creation",
                side_effect=kuiqctl.KuiqctlError("artifact unavailable"),
            ),
            mock.patch.object(kuiqctl, "reset_cluster") as reset,
        ):
            with self.assertRaisesRegex(kuiqctl.KuiqctlError, "artifact unavailable"):
                kuiqctl.recreate(config, True)
        reset.assert_not_called()


if __name__ == "__main__":
    unittest.main()
