#!/usr/bin/env bash
#
#   setup_head.bash: Standard first part of all setup scripts
#
set -Eeuo pipefail

die() {
    local exitcode="$1"; shift
    echo 1>&2 "$(basename "$0")" "$@"
    exit $exitcode
}

####################################################################
