#!/usr/bin/env bash
set -euo pipefail

export LC_ALL=C

usage() {
  printf '%s\n' \
    'usage: verify-executor-abi.sh <executor-binary> [maximum-glibc]' \
    '       verify-executor-abi.sh --check-version <required> <maximum>' >&2
  exit 2
}

valid_version() {
  [[ $1 =~ ^[0-9]+([.][0-9]+){1,2}$ ]]
}

version_is_compatible() {
  local required=$1
  local maximum=$2
  local highest

  valid_version "$required" && valid_version "$maximum" || return 2
  highest=$(printf '%s\n%s\n' "$required" "$maximum" | sort -V | tail -n 1)
  [[ $highest == "$maximum" ]]
}

if [[ ${1:-} == --check-version ]]; then
  [[ $# -eq 3 ]] || usage
  if ! version_is_compatible "$2" "$3"; then
    printf 'executor_abi=incompatible max_glibc=%s allowed_glibc=%s\n' "$2" "$3" >&2
    exit 1
  fi
  printf 'executor_abi=compatible max_glibc=%s allowed_glibc=%s\n' "$2" "$3"
  exit 0
fi

[[ $# -ge 1 && $# -le 2 ]] || usage
binary=$1
maximum=${2:-2.36}

valid_version "$maximum" || {
  printf 'verify-executor-abi: invalid maximum glibc version: %s\n' "$maximum" >&2
  exit 2
}
[[ -f $binary && -x $binary ]] || {
  printf 'verify-executor-abi: executable file required: %s\n' "$binary" >&2
  exit 2
}
for command in awk grep readelf sed sha256sum sort tail; do
  command -v "$command" >/dev/null || {
    printf 'verify-executor-abi: required command is absent: %s\n' "$command" >&2
    exit 2
  }
done

header=$(readelf -h -- "$binary")
elf_class=$(awk -F: '/^[[:space:]]*Class:/{gsub(/^[[:space:]]+/, "", $2); print $2; exit}' <<<"$header")
machine=$(awk -F: '/^[[:space:]]*Machine:/{gsub(/^[[:space:]]+/, "", $2); print $2; exit}' <<<"$header")
if [[ $elf_class != ELF64 || $machine != *X86-64* ]]; then
  printf 'verify-executor-abi: expected ELF64 x86-64; got class=%s machine=%s\n' \
    "${elf_class:-unknown}" "${machine:-unknown}" >&2
  exit 1
fi

version_info=$(readelf --version-info -- "$binary")
versions=$(grep -oE 'GLIBC_[0-9]+([.][0-9]+){1,2}' <<<"$version_info" | \
  sed 's/^GLIBC_//' | sort -Vu || true)
max_glibc=$(tail -n 1 <<<"$versions")
if [[ -n $max_glibc ]] && ! version_is_compatible "$max_glibc" "$maximum"; then
  printf 'executor_abi=incompatible architecture=x86_64 max_glibc=%s allowed_glibc=%s\n' \
    "$max_glibc" "$maximum" >&2
  exit 1
fi

digest=$(sha256sum -- "$binary" | awk '{print $1}')
printf 'executor_abi=compatible architecture=x86_64 max_glibc=%s allowed_glibc=%s sha256=%s\n' \
  "${max_glibc:-none}" "$maximum" "$digest"
