# quick-prod-k8s

`kuiqctl` creates and manages a persistent, single-node **kubeadm** Kubernetes cluster
on a Debian/Ubuntu systemd host. Kubeadm is the only and default backend. The
cluster uses containerd and Calico, and a small network watcher runs as a
service, so everything survives logout and reboot. It manages one host-global cluster
at a time; `cluster_name` controls its kubeconfig identity rather than creating
several isolated clusters on the same machine.

## Install and create

```bash
# On a new machine:
git clone <repository-url> quick-prod-k8s
cd quick-prod-k8s
sudo ./install.sh
command -v kuiqctl
sudo kuiqctl create
sudo kuiqctl kubeconfig --output "$HOME/.kube/quick-prod.yaml"
export KUBECONFIG="$HOME/.kube/quick-prod.yaml"
kubectl get nodes
```

`install.sh` places `kuiqctl` in `/usr/local/bin`, its public configuration in
`/etc/kuiqctl/config.json`, and its watcher in systemd. After that, commands can
be run from any directory. Lifecycle and kubeconfig commands require `sudo`;
running one without it returns a direct permission message.

Creation installs kubeadm, kubelet, kubectl, containerd, Calico, and Avahi from
their current configured repositories. The default configuration permits API access through UFW from
`192.168.0.0/24` (office) and `192.168.1.0/24` (home). Edit
`/etc/kuiqctl/config.json` before creation to change those networks,
cluster virtual networks, Kubernetes minor, name, or endpoint.

If Docker already installed `containerd.io`, kuiqctl reuses its `containerd`
binary. It does not request Ubuntu's conflicting `containerd` package.

## Where the workflow is implemented

The workflow is Python in the repository's `kuiqctl` executable; it does not
depend on Ansible. The main functions are:

- `prepare_host()` — packages, containerd, kernel modules, sysctl, swap and mDNS.
- `write_kubeadm_config()` — generates the kubeadm v1beta4 configuration.
- `create()` — validates, runs `kubeadm init`, installs Calico and waits for Ready.
- `reset_cluster()` — runs `kubeadm reset` and removes kuiqctl-owned CNI state.
- `recreate()` — validates/prepares dependencies before destructive reset, then creates.

`install.sh` is intentionally small: it only installs the executable,
configuration, and systemd unit.

## Lifecycle commands

```bash
sudo kuiqctl status
sudo kuiqctl recreate --yes
sudo kuiqctl remove --yes
```

`recreate` and `remove` permanently delete workloads, Kubernetes objects, and
the local kubeadm/etcd state. They preserve the kuiqctl configuration. The explicit
`--yes` flag prevents accidental resets.

## Moving between networks

By default, the exported kubeconfig uses `<hostname>.local`, and creation
installs/enables Avahi. mDNS resolves that stable name to the host's current
address on either LAN. Internally, kubeadm, kubelet, and local etcd use the
host-only `stable_node_ip` (`10.255.255.1/32` by default), which is kept on the
loopback interface by `kuiqctl-agent.service`. The API certificate
contains the roaming hostname and stable internal address. Consequently, a LAN
change does not leave etcd or static control-plane manifests bound to an old
DHCP address.

This works when the kubectl client is on the same multicast-capable LAN. Some
corporate and guest Wi-Fi networks block mDNS or isolate clients. In that case,
set `endpoint` to a stable DNS name, Tailscale MagicDNS name, or another routed
name before creating the cluster. Both networks must also allow TCP 6443 to the
host. CIDR values cannot be placed in a TLS certificate; an IP SAN represents
only one IP, which is why the stable name is essential.

The Pod (`10.244.0.0/16`), Service (`10.96.0.0/12`), stable node IP, and client
LANs are validated against each other. Change them before initial creation if
they overlap any LAN, VPN, or routed network you use.

## Operational notes

- `kuiqctl create` refuses an existing kubeadm cluster instead of guessing.
- The default Kubernetes minor is `1.37`; packages are pinned with `apt-mark`
  after installation. Change `kubernetes_minor` before creation when needed.
- Calico is pinned to the configured manifest version (`v3.32.1` by default).
- Swap is disabled at runtime when creating the cluster and by the kuiqctl watcher
  before kubelet on boot; `/etc/fstab` is not modified.
- The generated admin kubeconfig is mode `0600`; treat it as a root-equivalent
  credential.
- Inspect the watcher with
  `journalctl -u kuiqctl-agent.service -f`.
- This is a quick single-host cluster, not high availability. The stable
  host-only node address is intended for a single node; adding remote workers
  requires a routed stable control-plane design.
