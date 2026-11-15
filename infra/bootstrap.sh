#!/bin/sh
set -eu

# O provisionador ansible_local usa o pacote da mesma distribuição das VMs.
if ! command -v ansible-playbook >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y ansible
fi
