# Changelog

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
