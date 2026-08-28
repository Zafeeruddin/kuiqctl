# Changelog

## Unreleased

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
