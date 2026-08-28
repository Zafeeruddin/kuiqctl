#!/usr/bin/env bash
set -Eeuo pipefail

version=${1:-}
output_dir=${2:-dist}

if [[ -z ${version} ]]; then
  echo "Usage: $0 VERSION [OUTPUT_DIR]" >&2
  exit 2
fi
version=${version#v}
if [[ ! ${version} =~ ^[0-9]+\.[0-9]+\.[0-9]+([.+-][0-9A-Za-z.-]+)?$ ]]; then
  echo "build-release.sh: invalid version: ${version}" >&2
  exit 2
fi

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
reported_version=$("$repo_dir/kuiqctl" --version | awk '{print $2}')
if [[ ${reported_version} != "${version}" ]]; then
  echo "build-release.sh: tag/archive version ${version} does not match kuiqctl ${reported_version}" >&2
  exit 1
fi

mkdir -p -- "$output_dir"
output_dir=$(cd -- "$output_dir" && pwd)
stage=$(mktemp -d /tmp/kuiqctl-release.XXXXXX)
trap 'rm -rf -- "$stage"' EXIT
archive_root="kuiqctl-v${version}"
install -d -m 0755 "$stage/$archive_root" "$stage/$archive_root/assets"

install -m 0755 "$repo_dir/kuiqctl" "$stage/$archive_root/kuiqctl"
install -m 0755 "$repo_dir/install.sh" "$stage/$archive_root/install.sh"
install -m 0755 "$repo_dir/uninstall.sh" "$stage/$archive_root/uninstall.sh"
install -m 0755 "$repo_dir/scripts/build-release.sh" "$stage/$archive_root/build-release.sh"
install -m 0644 "$repo_dir/kuiqctl-agent.service" "$stage/$archive_root/kuiqctl-agent.service"
install -m 0644 "$repo_dir/config.example.json" "$stage/$archive_root/config.example.json"
install -m 0644 "$repo_dir/README.md" "$stage/$archive_root/README.md"
install -m 0644 "$repo_dir/CHANGELOG.md" "$stage/$archive_root/CHANGELOG.md"
install -m 0644 "$repo_dir/CONTRIBUTING.md" "$stage/$archive_root/CONTRIBUTING.md"
install -m 0644 "$repo_dir/SECURITY.md" "$stage/$archive_root/SECURITY.md"
install -m 0644 "$repo_dir/LICENSE" "$stage/$archive_root/LICENSE"
for asset in "$repo_dir"/assets/*; do
  install -m 0644 "$asset" "$stage/$archive_root/assets/$(basename "$asset")"
done

archive="$output_dir/${archive_root}.tar.gz"
tar \
  --sort=name \
  --mtime="@${SOURCE_DATE_EPOCH:-0}" \
  --owner=0 \
  --group=0 \
  --numeric-owner \
  -C "$stage" \
  -cf - \
  "$archive_root" | gzip -n >"$archive"

(
  cd -- "$output_dir"
  sha256sum "${archive_root}.tar.gz" >"${archive_root}.tar.gz.sha256"
)

echo "Created $archive"
echo "Created ${archive}.sha256"
