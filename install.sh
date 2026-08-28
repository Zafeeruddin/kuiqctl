#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "install.sh must run as root (use sudo)" >&2
  exit 1
fi

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
install -m 0755 "$repo_dir/qpk" /usr/local/bin/qpk
install -m 0644 "$repo_dir/quick-prod-k8s-agent.service" /etc/systemd/system/quick-prod-k8s-agent.service
install -d -m 0755 /etc/quick-prod-k8s
if [[ ! -e /etc/quick-prod-k8s/config.json ]]; then
  install -m 0600 "$repo_dir/config.example.json" /etc/quick-prod-k8s/config.json
elif grep -q '"k3s_channel"' /etc/quick-prod-k8s/config.json; then
  cp -p /etc/quick-prod-k8s/config.json /etc/quick-prod-k8s/config.json.k3s-backup
  install -m 0600 "$repo_dir/config.example.json" /etc/quick-prod-k8s/config.json
  echo "Migrated the old K3s configuration; backup: /etc/quick-prod-k8s/config.json.k3s-backup"
fi
systemctl daemon-reload
echo "Installed qpk. Edit /etc/quick-prod-k8s/config.json if needed, then run: sudo qpk create"
