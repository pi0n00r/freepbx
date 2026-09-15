#!/usr/bin/env bash
# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=crustacea
set -Eeuo pipefail
CORE_TGZ=${1:?accepted pinned package required}
export CORE_TGZ
source "$(dirname -- "${BASH_SOURCE[0]}")/openclaw-core-install.commands"
