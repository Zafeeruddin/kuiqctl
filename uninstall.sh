#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: sudo ./uninstall.sh [--purge-config]

Uninstall the kuiqctl CLI and its owned service/runtime files.
The cluster must be removed first. Configuration is preserved unless
--purge-config is supplied.
EOF
}

purge_config=false
case ${1:-} in
  "") ;;
  --purge-config) purge_config=true ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    echo "uninstall.sh: unknown option: $1" >&2
    usage >&2
    exit 2
    ;;
esac
if [[ $# -gt 1 ]]; then
  echo "uninstall.sh: too many arguments" >&2
  usage >&2
  exit 2
fi

if [[ ${EUID} -ne 0 ]]; then
  echo "uninstall.sh must run as root (use sudo)" >&2
  exit 1
fi

cluster_state=false
for marker in \
  /etc/kubernetes/admin.conf \
  /etc/kubernetes/manifests/kube-apiserver.yaml \
  /etc/kubernetes/pki/ca.crt \
  /var/lib/etcd/member; do
  if [[ -e ${marker} ]]; then
    cluster_state=true
    break
  fi
done

if [[ ${cluster_state} == true ]]; then
  cat >&2 <<'EOF'
uninstall.sh: Kubernetes cluster state still exists.

Refusing to uninstall while a cluster may be live. Remove it first:

  sudo kuiqctl remove --yes

Then rerun this script. This guard prevents removal of the network watcher
or CLI while the cluster still depends on the stable node address.
EOF
  exit 1
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl disable --now kuiqctl-agent.service >/dev/null 2>&1 || true
fi

rm -f -- /etc/systemd/system/kuiqctl-agent.service
rm -f -- /usr/local/bin/kuiqctl
rm -f -- /etc/modules-load.d/kuiqctl.conf
rm -f -- /etc/sysctl.d/99-kuiqctl.conf
rm -f -- /etc/kubernetes/kuiqctl-kubeadm.yaml
rm -f -- /var/cache/kuiqctl/calico.yaml
rmdir -- /var/cache/kuiqctl 2>/dev/null || true
rm -f -- /run/kuiqctl/primary-ip
rmdir -- /run/kuiqctl 2>/dev/null || true
rm -f -- /run/lock/kuiqctl.lock

if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
fi

if [[ ${purge_config} == true ]]; then
  rm -f -- /etc/kuiqctl/config.json
  rmdir -- /etc/kuiqctl 2>/dev/null || true
  echo "Removed /etc/kuiqctl/config.json. Any migration backup in /etc/kuiqctl was preserved."
else
  echo "Preserved /etc/kuiqctl/config.json (use --purge-config to remove it)."
fi

cat <<'EOF'
Uninstalled kuiqctl.

Kubernetes packages, package holds, containerd and its configuration/backup,
the Kubernetes apt repository, Avahi, UFW rules, and unrelated CNI/runtime
state were left unchanged.
EOF
