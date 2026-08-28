# Contributing

Thanks for helping improve kuiqctl. Keep changes focused: this project manages
a persistent, single-node kubeadm cluster on Debian/Ubuntu systemd hosts.

## Development setup

- Linux with Python 3.10 or newer
- Bash
- No Python packages are required for the unit tests
- A real Debian/Ubuntu systemd host is required only for manual lifecycle tests

Run the local checks before opening a pull request:

```bash
python3 -m py_compile kuiqctl tests/test_kuiqctl.py
python3 -m unittest discover -s tests -v
bash -n install.sh uninstall.sh scripts/build-release.sh
./kuiqctl --help
./kuiqctl --version
```

Open an issue before large behavioral or architecture changes. Pull requests
should explain the problem, the safety impact, and how the change was tested.
Add unit tests for logic that can be exercised without a Kubernetes host.

For kubeadm or network bugs, include the following when available:

```text
kuiqctl --version
sudo kuiqctl doctor
OS and version
kubeadm / Kubernetes version
home, office, VPN, DNS, and mDNS network context
relevant journalctl output for kubelet, containerd, or kuiqctl-agent
```

Redact public IPs, private hostnames if sensitive, usernames, registry details,
and other identifying network information. Never attach credentials, tokens,
private keys, certificates, or an administrator kubeconfig.
