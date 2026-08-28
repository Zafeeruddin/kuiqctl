#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "install.sh must run as root (use sudo)" >&2
  exit 1
fi

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
install -m 0755 "$repo_dir/kuiqctl" /usr/local/bin/kuiqctl
install -m 0644 "$repo_dir/kuiqctl-agent.service" /etc/systemd/system/kuiqctl-agent.service
install -d -m 0755 /etc/kuiqctl
if [[ ! -e /etc/kuiqctl/config.json ]]; then
  if [[ -e /etc/quick-prod-k8s/config.json ]] && ! grep -q '"k3s_channel"' /etc/quick-prod-k8s/config.json; then
    install -m 0644 /etc/quick-prod-k8s/config.json /etc/kuiqctl/config.json
    echo "Migrated configuration from /etc/quick-prod-k8s/config.json"
  else
    install -m 0644 "$repo_dir/config.example.json" /etc/kuiqctl/config.json
    if [[ -e /etc/quick-prod-k8s/config.json ]]; then
      cp -p /etc/quick-prod-k8s/config.json /etc/kuiqctl/config.json.k3s-backup
      echo "Saved the old K3s configuration as /etc/kuiqctl/config.json.k3s-backup"
    fi
  fi
elif grep -q '"k3s_channel"' /etc/kuiqctl/config.json; then
  cp -p /etc/kuiqctl/config.json /etc/kuiqctl/config.json.k3s-backup
  install -m 0644 "$repo_dir/config.example.json" /etc/kuiqctl/config.json
  echo "Migrated the old K3s configuration; backup: /etc/kuiqctl/config.json.k3s-backup"
fi
chmod 0644 /etc/kuiqctl/config.json
if systemctl list-unit-files quick-prod-k8s-agent.service >/dev/null 2>&1; then
  systemctl disable --now quick-prod-k8s-agent.service >/dev/null 2>&1 || true
fi
systemctl daemon-reload
echo "Installed kuiqctl. Edit /etc/kuiqctl/config.json if needed, then run: sudo kuiqctl create"
