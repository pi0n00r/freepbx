#!/bin/sh
# AI-NOTICE:License=AGPL-3.0-or-later
set -eu

usage() {
    echo "usage: $0 --check|--install --expected-unit-sha256 SHA256" >&2
    exit 2
}

action=
expected=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --check|--install) action=$1 ;;
        --expected-unit-sha256)
            [ "$#" -ge 2 ] || usage
            expected=$2
            shift
            ;;
        *) usage ;;
    esac
    shift
done
[ -n "$action" ] && [ "${#expected}" -eq 64 ] || usage

src=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/10-vm-shutdown-budget.conf
root=${FREEPBX_VM_FIXTURE_ROOT:-}
unit="$root/lib/systemd/system/freepbx.service"
target_dir="$root/etc/systemd/system/freepbx.service.d"
target="$target_dir/10-vm-shutdown-budget.conf"

[ -f "$src" ] || { echo "source_dropin_missing" >&2; exit 1; }
[ -f "$unit" ] || { echo "freepbx_unit_missing" >&2; exit 1; }
actual=$(sha256sum "$unit" | awk '{print $1}')
[ "$actual" = "$expected" ] || { echo "freepbx_unit_preimage_mismatch" >&2; exit 1; }

if [ -z "$root" ]; then
    [ "$(id -u)" -eq 0 ] || { echo "root_required" >&2; exit 1; }
    [ "$(systemd-detect-virt 2>/dev/null || true)" = kvm ] || { echo "kvm_required" >&2; exit 1; }
    systemctl is-active --quiet qemu-guest-agent.service || { echo "qemu_guest_agent_inactive" >&2; exit 1; }
    systemctl is-active --quiet freepbx.service || { echo "freepbx_inactive" >&2; exit 1; }
    systemctl cat freepbx.service | grep -Fq 'ExecStop=/usr/sbin/fwconsole stop' || {
        echo "supported_freepbx_stop_missing" >&2; exit 1;
    }
    findmnt -no OPTIONS / | tr ',' '\n' | grep -qx rw || { echo "root_not_writable" >&2; exit 1; }
    channels=$(/usr/sbin/asterisk -rx 'core show channels')
    printf '%s\n' "$channels" | grep -Fq '0 active channels' || { echo "active_channels" >&2; exit 1; }
    printf '%s\n' "$channels" | grep -Fq '0 active calls' || { echo "active_calls" >&2; exit 1; }
fi

if [ -e "$target" ] && ! cmp -s "$src" "$target"; then
    echo "dropin_conflict" >&2
    exit 1
fi

if [ "$action" = --install ] && [ ! -e "$target" ]; then
    if [ -n "$root" ]; then
        install -d -m 0755 "$target_dir"
    else
        install -d -m 0755 -o root -g root "$target_dir"
    fi
    tmp="$target_dir/.10-vm-shutdown-budget.conf.$$"
    trap 'rm -f "$tmp"' EXIT HUP INT TERM
    if [ -n "$root" ]; then
        install -m 0644 "$src" "$tmp"
    else
        install -m 0644 -o root -g root "$src" "$tmp"
    fi
    sync "$tmp"
    mv -T "$tmp" "$target"
    trap - EXIT HUP INT TERM
fi

if [ -e "$target" ]; then
    cmp -s "$src" "$target" || { echo "dropin_readback_mismatch" >&2; exit 1; }
    if [ -z "$root" ]; then
        [ "$(stat -c '%a:%u:%g' "$target")" = 644:0:0 ] || { echo "dropin_metadata_mismatch" >&2; exit 1; }
    else
        [ "$(stat -c '%a' "$target")" = 644 ] || { echo "dropin_metadata_mismatch" >&2; exit 1; }
    fi
fi

if [ -z "$root" ] && [ "$action" = --install ]; then
    systemctl daemon-reload
    [ "$(systemctl show freepbx.service -p TimeoutStopUSec --value)" = 4min ] || {
        echo "effective_timeout_mismatch" >&2; exit 1;
    }
fi

if [ "$action" = --check ] && [ ! -e "$target" ]; then
    echo "check_pass_not_installed"
else
    echo "installed_verify_pass"
fi
