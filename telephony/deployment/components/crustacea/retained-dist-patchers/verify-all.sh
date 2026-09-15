#!/usr/bin/env bash
# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=crustacea
# AI-NOTICE:Repository=https://github.com/pi0n00r/crustacea-backup
# AI-NOTICE:Network-Service=AGPL §13 applies when this file is part of a network-exposed service

# Read-only post-upgrade gate for every mandatory dist patch in apply-all.sh.
# Deployment/startup integration must run this gate before launching an upgraded
# package; wiring it into the gateway systemd unit remains pending.

set -euo pipefail

DIST=${OPENCLAW_DIST:-/usr/lib/node_modules/openclaw/dist}

largest_target() {
    local pattern=$1
    local target
    target=$(find "$DIST" -maxdepth 1 -type f -name "$pattern" \
        ! -name '*.bak.*' ! -name '*.upstream-*' -printf '%s %p\n' \
        | sort -nr | head -1 | cut -d' ' -f2-)
    if [ -z "$target" ]; then
        echo "missing dist target: $DIST/$pattern" >&2
        return 1
    fi
    printf '%s\n' "$target"
}

largest_ui_target() {
    local pattern=$1
    local target
    target=$(find "$DIST/control-ui/assets" -maxdepth 1 -type f -name "$pattern" \
        ! -name '*.bak.*' ! -name '*.upstream-*' -printf '%s %p\n' \
        | sort -nr | head -1 | cut -d' ' -f2-)
    if [ -z "$target" ]; then
        echo "missing Control UI target: $DIST/control-ui/assets/$pattern" >&2
        return 1
    fi
    printf '%s\n' "$target"
}

require_sentinel() {
    local target=$1
    local sentinel=$2
    local patch=$3
    if ! grep -Fq "$sentinel" "$target"; then
        echo "missing mandatory patch: $patch" >&2
        echo "target: $target" >&2
        echo "sentinel: $sentinel" >&2
        return 1
    fi
    printf 'verified: %s\n' "$patch"
}

require_native_dual_stack_runtime() {
    local target=$1
    grep -Fq 'function resolveSelfAddresses()' "$target" &&
        grep -Fq 'const addresses = resolveSelfAddresses();' "$target" &&
        grep -Fq 'addresses,' "$target" || {
        echo "missing source-maintained dual-stack runtime contract" >&2
        echo "target: $target" >&2
        return 1
    }
    printf 'verified: source-maintained dual-stack presence runtime\n'
}

require_native_dual_stack_ui() {
    local target=$1
    grep -Fq 'addresses.filter' "$target" || {
        echo "missing source-maintained dual-stack UI contract" >&2
        echo "target: $target" >&2
        return 1
    }
    printf 'verified: source-maintained dual-stack presence UI\n'
}

require_native_dist_contract() {
    local contract=$1
    shift
    local marker
    for marker in "$@"; do
        if ! find "$DIST" -maxdepth 2 -type f \
            \( -name '*.js' -o -name '*.mjs' \) \
            -exec bash -c '
                rc=0
                grep -Fl -- "$@" || rc=$?
                case "$rc" in
                    0|1) exit 0 ;;
                    *) exit "$rc" ;;
                esac
            ' bash "$marker" {} + | grep . >/dev/null; then
            echo "missing source-maintained $contract contract" >&2
            echo "dist: $DIST" >&2
            echo "marker: $marker" >&2
            return 1
        fi
    done
    printf 'verified: source-maintained %s contract\n' "$contract"
}

dreaming_phases=$(largest_target 'dreaming-phases-*.*js')
dreaming_narrative=$(largest_target 'dreaming-narrative-*.*js')
session_ingestion=$(largest_target 'session-ingestion-*.*js')
system_presence=$(largest_target 'system-presence-*.*js')
devices_page=$(largest_ui_target 'devices-page-*.js')

require_sentinel "$session_ingestion" 'isCorpusNoiseSnippet' \
    'oc-corpus-noise-filter-patch.py'
require_sentinel "$session_ingestion" 'isAnthropicTaintedSnippet' \
    'oc-corpus-taint-filter-patch.py'
require_sentinel "$dreaming_phases" \
    'Phase 5.19f: no-artifacts is legitimate clean exit' \
    'oc-rem-narrative-firegate-patch.py'
require_sentinel "$dreaming_narrative" \
    'Phase 5.19i: LocalAI Gemma4 needs 300s narrative timeout' \
    'oc-narrative-timeout-extend-patch.py'
require_sentinel "$dreaming_narrative" \
    'const NARRATIVE_TIMEOUT_MS = 3e5;' \
    'oc-narrative-timeout-extend-patch.py constant'
require_native_dist_contract 'CSR 871-C response classifier' \
    'function classifyCsr871cRefusalResult(' \
    'csr_871c_response_refusal_detected'
require_native_dual_stack_runtime "$system_presence"
require_native_dual_stack_ui "$devices_page"
require_native_dist_contract 'MCP private-network' \
    'function getPrivateNetworkOptIn(' \
    'allowPrivateNetwork: resolved.allowPrivateNetwork' \
    'mergeSsrFPolicies(' \
    'params.allowPrivateNetwork ? { allowPrivateNetwork: true } : void 0'
require_native_dist_contract 'dual-stack listener' \
    'const listenHost = bindHost === "0.0.0.0" ? "::" : bindHost;' \
    'host: listenHost,' \
    'ipv6Only: false'

echo "all mandatory Crustacea dist patches and source-maintained contracts verified"
