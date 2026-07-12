#!/bin/bash

set -e
user="";
if [ -n "$1" ]; then
    user="$1"@
fi
ssh "$user"login.toolforge.org <<'ENDSSH'
become credit-my-cc

echo "Build from main branch..."
toolforge build start https://github.com/lokal-profil/credit-my-cc_2.git

echo "Restart service..."
toolforge webservice buildservice restart --mount=none

ENDSSH
