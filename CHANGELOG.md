# Changelog

## Unreleased

- Keep the stable loopback API endpoint in the invoking user's local default
  kubeconfig and fully rename its context, avoiding DNS/proxy interception and
  collisions with an existing kubeadm context.
- Detect and terminate verified stale control-plane processes that continue
  holding Kubernetes ports after kubeadm and CRI cleanup.
- Force-remove CRI containers and pod sandboxes left behind by kubeadm's
  best-effort reset before checking that control-plane ports were released.
- Configure `~/.kube/config` for the invoking user after successful creation,
  merging with an existing file so `kubectl` works without extra exports.
- Pin both crictl's runtime and image-service endpoints to containerd when
  pre-pulling Calico images, ignoring stale CRI-O client configuration.
- Install and validate the `cri-tools` dependency used to pre-pull Calico
  images, and report missing executables without a Python traceback.
- Accept the destructive `--yes` confirmation flag before or after `recreate`
  and `remove`.
- Add `kuiqctl doctor` for actionable checks of an existing cluster, its
  stable node identity, roaming endpoint, services, API, node, and Calico.
- Add a guarded `uninstall.sh` that preserves configuration by default and
  refuses to run while cluster state exists.
- Add CI for Python, unit, shell, configuration, CLI, and release-archive
  validation.
- Prepare reproducible tagged release archives with SHA256 checksums.
- Document host changes, removal and uninstall boundaries, limitations, and
  contributor and security reporting workflows.

## v0.1.0 - 2026-08-28

First public release.

- Create, inspect, recreate, and remove a single-node kubeadm cluster.
- Install and configure containerd, kubelet, kubectl, and Calico.
- Keep the control plane stable when the host moves between local networks.
- Check routes, DNS, manifests, images, stale state, and occupied ports before
  cluster creation.
- Prepare external artifacts before resetting a cluster during recreation.
- Export a kubeconfig that uses the host's roaming endpoint.
- Maintain the stable node address with a systemd service across reboots.
