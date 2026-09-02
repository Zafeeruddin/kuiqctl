import importlib.machinery
import importlib.util
import io
import json
import os
import pathlib
import subprocess
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

    def test_installs_and_holds_cri_tools_with_kubernetes_packages(self):
        self.assertIn("cri-tools", kuiqctl.KUBERNETES_PACKAGES)

    def test_package_stack_requires_crictl(self):
        config = kuiqctl.defaults()

        def which(binary):
            return None if binary == "crictl" else f"/usr/bin/{binary}"

        with mock.patch.object(kuiqctl.shutil, "which", side_effect=which):
            self.assertFalse(kuiqctl.package_stack_ready(config))

    def test_missing_command_is_reported_without_a_traceback(self):
        with mock.patch.object(kuiqctl.subprocess, "run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(kuiqctl.KuiqctlError, "required command not found: crictl"):
                kuiqctl.run(["crictl", "info"])

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

    def test_installs_default_kubeconfig_for_invoking_user(self):
        config = kuiqctl.defaults()
        config["endpoint"] = "node.local"
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            admin = root / "admin.conf"
            admin.write_text(
                "server: https://10.255.255.1:6443\n"
                "name: kubernetes\n"
                "current-context: kubernetes-admin\n"
            )
            with (
                mock.patch.object(kuiqctl, "ADMIN_CONF", admin),
                mock.patch.object(kuiqctl, "invoking_user", return_value=("alice", root, 1000, 1000)),
                mock.patch.object(kuiqctl.os, "chown"),
            ):
                destination = kuiqctl.install_default_kubeconfig(config)
            rendered = destination.read_text()
            self.assertEqual(destination, root / ".kube" / "config")
            self.assertIn("https://node.local:6443", rendered)
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
            self.assertEqual(destination.parent.stat().st_mode & 0o777, 0o700)

    def test_merges_an_existing_default_kubeconfig(self):
        config = kuiqctl.defaults()
        config["endpoint"] = "node.local"
        completed = subprocess.CompletedProcess(
            ["kubectl"], 0, stdout="merged kubeconfig\n", stderr=""
        )
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            admin = root / "admin.conf"
            admin.write_text("server: https://10.255.255.1:6443\n")
            destination = root / ".kube" / "config"
            destination.parent.mkdir()
            destination.write_text("existing kubeconfig\n")
            with (
                mock.patch.object(kuiqctl, "ADMIN_CONF", admin),
                mock.patch.object(kuiqctl, "invoking_user", return_value=("alice", root, 1000, 1000)),
                mock.patch.object(kuiqctl.os, "chown"),
                mock.patch.object(kuiqctl, "run", return_value=completed) as run,
            ):
                kuiqctl.install_default_kubeconfig(config)
            self.assertEqual(destination.read_text(), "merged kubeconfig\n")
            self.assertEqual(run.call_args.args[0], ["kubectl", "config", "view", "--flatten", "--raw"])
            kubeconfigs = run.call_args.kwargs["env"]["KUBECONFIG"].split(os.pathsep)
            self.assertEqual(pathlib.Path(kubeconfigs[1]), destination)


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

    def test_calico_pull_uses_containerd_for_runtime_and_images(self):
        completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with (
            mock.patch.object(kuiqctl, "calico_images", return_value=["quay.io/calico/cni:v3.32.1"]),
            mock.patch.object(kuiqctl, "run", return_value=completed) as run,
        ):
            kuiqctl.pull_required_images()
        command = run.call_args_list[1].args[0]
        self.assertEqual(
            command,
            [
                "crictl",
                "--runtime-endpoint",
                kuiqctl.CRI_SOCKET,
                "--image-endpoint",
                kuiqctl.CRI_SOCKET,
                "pull",
                "quay.io/calico/cni:v3.32.1",
            ],
        )

    def test_cri_cleanup_force_removes_containers_and_pod_sandboxes(self):
        completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with mock.patch.object(kuiqctl, "run", return_value=completed) as run:
            kuiqctl.remove_remaining_cri_workloads(kuiqctl.CRI_SOCKET)
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                kuiqctl.crictl_command(kuiqctl.CRI_SOCKET, "rm", "--force", "--all"),
                kuiqctl.crictl_command(kuiqctl.CRI_SOCKET, "rmp", "--force", "--all"),
            ],
        )

    def test_port_owner_parser_extracts_every_pid(self):
        completed = subprocess.CompletedProcess(
            [],
            0,
            stdout='LISTEN 0 4096 127.0.0.1:10259 0.0.0.0:* users:(("kube-scheduler",pid=2999,fd=3))\n',
            stderr="",
        )
        with mock.patch.object(kuiqctl, "run", return_value=completed):
            self.assertEqual(kuiqctl.port_owner_pids(10259), {2999})

    def test_stale_control_plane_cleanup_kills_only_matching_components(self):
        owners = {10257: {3001}, 10259: {2999}, 6443: {4000}}
        active = {3001, 2999, 4000}

        def matches(pid, expected):
            return pid in active and (pid, expected) in {
                (3001, "kube-controller-manager"),
                (2999, "kube-scheduler"),
            }

        def kill_process(pid, _signal):
            active.discard(pid)

        with (
            mock.patch.object(kuiqctl, "port_owner_pids", side_effect=lambda port: owners.get(port, set())),
            mock.patch.object(kuiqctl, "process_matches", side_effect=matches),
            mock.patch.object(kuiqctl.os, "kill", side_effect=kill_process) as kill,
        ):
            kuiqctl.stop_stale_control_plane_processes()
        self.assertEqual(
            {call.args for call in kill.call_args_list},
            {(3001, kuiqctl.signal.SIGTERM), (2999, kuiqctl.signal.SIGTERM)},
        )

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


class CliTests(unittest.TestCase):
    def test_yes_is_accepted_before_recreate(self):
        args = kuiqctl.parser().parse_args(["--yes", "recreate"])
        self.assertTrue(args.yes)

    def test_yes_is_accepted_after_recreate(self):
        args = kuiqctl.parser().parse_args(["recreate", "--yes"])
        self.assertTrue(args.yes)

    def test_yes_is_accepted_before_and_after_remove(self):
        self.assertTrue(kuiqctl.parser().parse_args(["--yes", "remove"]).yes)
        self.assertTrue(kuiqctl.parser().parse_args(["remove", "--yes"]).yes)

    def test_yes_is_rejected_for_non_destructive_commands(self):
        with (
            mock.patch.object(kuiqctl, "require_root"),
            mock.patch("sys.stderr", new=io.StringIO()),
            self.assertRaisesRegex(SystemExit, "2"),
        ):
            kuiqctl.main(["--yes", "create"])


class DoctorTests(unittest.TestCase):
    NODE_JSON = json.dumps(
        {
            "items": [
                {
                    "metadata": {"name": "node-1"},
                    "status": {
                        "addresses": [
                            {"type": "InternalIP", "address": "10.255.255.1"},
                            {"type": "Hostname", "address": "node-1"},
                        ],
                        "conditions": [{"type": "Ready", "status": "True"}],
                    },
                }
            ]
        }
    )
    CALICO_JSON = json.dumps(
        {
            "status": {
                "desiredNumberScheduled": 1,
                "numberReady": 1,
                "numberUnavailable": 0,
            }
        }
    )

    def write_config(self, directory: str) -> pathlib.Path:
        config = kuiqctl.defaults()
        config["endpoint"] = "node.local"
        path = pathlib.Path(directory) / "config.json"
        path.write_text(json.dumps(config))
        return path

    def kubectl_result(self, args, **_kwargs):
        if args == ["get", "--raw=/readyz"]:
            return subprocess.CompletedProcess(args, 0, stdout="ok\n", stderr="")
        if args == ["get", "nodes", "-o", "json"]:
            return subprocess.CompletedProcess(args, 0, stdout=self.NODE_JSON, stderr="")
        if args == ["-n", "kube-system", "get", "daemonset", "calico-node", "-o", "json"]:
            return subprocess.CompletedProcess(args, 0, stdout=self.CALICO_JSON, stderr="")
        raise AssertionError(f"unexpected kubectl arguments: {args}")

    def test_node_health_reports_ready_stable_node(self):
        name, ready, addresses = kuiqctl.node_health(self.NODE_JSON, "10.255.255.1")
        self.assertEqual(name, "node-1")
        self.assertTrue(ready)
        self.assertEqual(addresses, ["10.255.255.1"])

    def test_calico_health_requires_every_desired_pod(self):
        healthy, detail = kuiqctl.calico_health(self.CALICO_JSON)
        self.assertTrue(healthy)
        self.assertEqual(detail, "1/1 calico-node pods Ready")
        unhealthy = json.dumps(
            {"status": {"desiredNumberScheduled": 1, "numberReady": 0, "numberUnavailable": 1}}
        )
        self.assertFalse(kuiqctl.calico_health(unhealthy)[0])

    def test_stable_ip_on_loopback_parses_ip_output(self):
        result = subprocess.CompletedProcess(
            ["ip"],
            0,
            stdout="1: lo    inet 127.0.0.1/8 scope host lo\\       valid_lft forever\n"
            "1: lo    inet 10.255.255.1/32 scope global lo\\       valid_lft forever\n",
            stderr="",
        )
        with mock.patch.object(kuiqctl, "run", return_value=result):
            self.assertTrue(kuiqctl.stable_ip_on_loopback("10.255.255.1"))
            self.assertFalse(kuiqctl.stable_ip_on_loopback("10.255.255.2"))

    def test_doctor_rejects_invalid_config_before_host_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = pathlib.Path(directory) / "config.json"
            config_path.write_text(json.dumps({"unexpected": True}))
            output = io.StringIO()
            with (
                mock.patch.object(kuiqctl, "require_root"),
                mock.patch.object(kuiqctl, "service_active") as service_active,
                mock.patch("sys.stdout", new=output),
            ):
                result = kuiqctl.doctor(config_path)
        self.assertEqual(result, 1)
        self.assertIn("[FAIL] config", output.getvalue())
        self.assertIn("unknown configuration keys", output.getvalue())
        service_active.assert_not_called()

    def test_doctor_reports_healthy_cluster(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = self.write_config(directory)
            admin_conf = pathlib.Path(directory) / "admin.conf"
            admin_conf.write_text("apiVersion: v1\n")
            output = io.StringIO()
            with (
                mock.patch.object(kuiqctl, "require_root"),
                mock.patch.object(kuiqctl, "ADMIN_CONF", admin_conf),
                mock.patch.object(kuiqctl, "service_active", return_value=True),
                mock.patch.object(kuiqctl, "stable_ip_on_loopback", return_value=True),
                mock.patch.object(kuiqctl, "primary_ip", return_value="192.168.1.20"),
                mock.patch.object(kuiqctl, "resolve_ipv4", return_value=["192.168.1.20"]),
                mock.patch.object(kuiqctl, "tcp_port_open", return_value=True),
                mock.patch.object(kuiqctl.shutil, "which", return_value="/usr/bin/kubectl"),
                mock.patch.object(kuiqctl, "kubectl", side_effect=self.kubectl_result),
                mock.patch("sys.stdout", new=output),
            ):
                result = kuiqctl.doctor(config_path)
        rendered = output.getvalue()
        self.assertEqual(result, 0)
        self.assertIn("[OK] config", rendered)
        self.assertIn("[OK] node Ready", rendered)
        self.assertIn("[OK] node InternalIP", rendered)
        self.assertIn("[OK] Calico", rendered)
        self.assertIn("Cluster healthy.", rendered)

    def test_doctor_treats_unavailable_mdns_as_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = self.write_config(directory)
            admin_conf = pathlib.Path(directory) / "admin.conf"
            admin_conf.write_text("apiVersion: v1\n")
            output = io.StringIO()
            with (
                mock.patch.object(kuiqctl, "require_root"),
                mock.patch.object(kuiqctl, "ADMIN_CONF", admin_conf),
                mock.patch.object(kuiqctl, "service_active", return_value=True),
                mock.patch.object(kuiqctl, "stable_ip_on_loopback", return_value=True),
                mock.patch.object(kuiqctl, "primary_ip", return_value="192.168.1.20"),
                mock.patch.object(kuiqctl, "resolve_ipv4", side_effect=OSError("mDNS unavailable")),
                mock.patch.object(kuiqctl, "tcp_port_open", return_value=True),
                mock.patch.object(kuiqctl.shutil, "which", return_value="/usr/bin/kubectl"),
                mock.patch.object(kuiqctl, "kubectl", side_effect=self.kubectl_result),
                mock.patch("sys.stdout", new=output),
            ):
                result = kuiqctl.doctor(config_path)
        rendered = output.getvalue()
        self.assertEqual(result, 0)
        self.assertIn("[WARN] endpoint", rendered)
        self.assertIn("resolvectl query node.local", rendered)
        self.assertIn("Cluster healthy, with 1 warning(s).", rendered)

    def test_doctor_failures_are_actionable(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = self.write_config(directory)
            output = io.StringIO()
            with (
                mock.patch.object(kuiqctl, "require_root"),
                mock.patch.object(kuiqctl, "ADMIN_CONF", pathlib.Path(directory) / "missing.conf"),
                mock.patch.object(kuiqctl, "service_active", return_value=False),
                mock.patch.object(kuiqctl, "stable_ip_on_loopback", return_value=False),
                mock.patch.object(kuiqctl, "primary_ip", return_value=""),
                mock.patch.object(kuiqctl, "resolve_ipv4", side_effect=OSError("mDNS unavailable")),
                mock.patch.object(kuiqctl, "tcp_port_open", return_value=False),
                mock.patch.object(kuiqctl.shutil, "which", return_value=None),
                mock.patch("sys.stdout", new=output),
            ):
                result = kuiqctl.doctor(config_path)
        rendered = output.getvalue()
        self.assertNotEqual(result, 0)
        self.assertIn("[FAIL] containerd", rendered)
        self.assertIn("Action: sudo systemctl restart containerd", rendered)
        self.assertIn("[FAIL] stable node IP", rendered)
        self.assertIn("Cluster unhealthy", rendered)


if __name__ == "__main__":
    unittest.main()
