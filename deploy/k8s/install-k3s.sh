#!/usr/bin/env bash
# Install k3s on the first VM, then join extra nodes.
# Run as a user who can sudo. Do this only after Terraform has printed the IPs.
set -euo pipefail

ROLE="${1:-server}"
K3S_URL="${K3S_URL:-}"
K3S_TOKEN="${K3S_TOKEN:-}"

if [[ "$ROLE" == "server" ]]; then
  curl -sfL https://get.k3s.io | sh -s - server \
    --write-kubeconfig-mode 644 \
    --disable traefik
  echo "Kubeconfig: /etc/rancher/k3s/k3s.yaml"
  echo "Node token: sudo cat /var/lib/rancher/k3s/server/node-token"
  echo "Next: install ingress-nginx and cert-manager (see RUNBOOK.md)."
elif [[ "$ROLE" == "agent" ]]; then
  if [[ -z "$K3S_URL" || -z "$K3S_TOKEN" ]]; then
    echo "Set K3S_URL=https://<server-ip>:6443 and K3S_TOKEN" >&2
    exit 1
  fi
  curl -sfL https://get.k3s.io | K3S_URL="$K3S_URL" K3S_TOKEN="$K3S_TOKEN" sh -s - agent
else
  echo "usage: $0 server|agent" >&2
  exit 1
fi
