#!/usr/bin/env bash
# bench/azure.sh — Run the benchmark natively on a fresh Azure VM and copy results back.
#
# Usage: bench/azure.sh --location REGION [bench/main.py options...]
# Requires: az CLI (logged in), ssh, rsync
set -euo pipefail

RG="kvc-bench-$(date +%s)"
VM="bench"
LOCATION=""
VM_SIZE="Standard_D2s_v3"
IMAGE="Canonical:ubuntu-24_04-lts:server:latest"
CUSTOM_IMAGE=false
ADMIN="bench"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

usage() {
    cat <<'EOF'
Usage: bench/azure.sh --location REGION [options] [bench/main.py options...]

Provisions an Azure VM, runs the benchmark natively, downloads results, then deletes the VM.

Options:
  --location REGION   Azure region (required). Find allowed regions with:
                        az account list-locations --query "[].name" -o tsv
  --image IMAGE_ID    use a pre-baked managed image instead of stock Ubuntu
                      (build one with bench/azure_build_image.sh)
  --vm-size SIZE      override VM size (default: Standard_D2s_v3)
  -h, --help          show this help

All other options are forwarded to bench/main.py (--version, --requests, etc.).
EOF
}

PASSTHROUGH=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --location) LOCATION="$2";              shift 2 ;;
        --image)    IMAGE="$2"; CUSTOM_IMAGE=true; shift 2 ;;
        --vm-size)  VM_SIZE="$2";               shift 2 ;;
        -h|--help)  usage; exit 0 ;;
        *)          PASSTHROUGH+=("$1"); shift ;;
    esac
done

if [[ -z "$LOCATION" ]]; then
    echo "error: --location is required" >&2
    echo "Run 'az account list-locations --query \"[].name\" -o tsv' to find allowed regions." >&2
    exit 1
fi

cleanup() {
    echo "==> Deleting resource group $RG (--no-wait)..."
    az group delete --name "$RG" --yes --no-wait 2>/dev/null || true
}
trap cleanup EXIT

echo "==> Creating VM ($VM_SIZE in $LOCATION)..."
az group create --name "$RG" --location "$LOCATION" -o none
az vm create \
    --resource-group "$RG" \
    --name "$VM" \
    --image "$IMAGE" \
    --size "$VM_SIZE" \
    --admin-username "$ADMIN" \
    --generate-ssh-keys \
    --public-ip-sku Standard \
    -o none

VM_IP=$(az vm show -g "$RG" -n "$VM" --show-details --query publicIps -o tsv)
SSH_OPTS=(-o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15)

echo "==> Waiting for SSH at $VM_IP..."
until ssh "${SSH_OPTS[@]}" "$ADMIN@$VM_IP" true 2>/dev/null; do sleep 5; done

if [[ "$CUSTOM_IMAGE" == "true" ]]; then
    echo "==> Using pre-baked image — skipping dep install."
else
    echo "==> Installing build tools + perf..."
    ssh "${SSH_OPTS[@]}" "$ADMIN@$VM_IP" bash -s <<'REMOTE'
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    build-essential python3 python3-pip \
    util-linux perl libc6-dbg \
    linux-tools-common
KVER=$(uname -r)
sudo apt-get install -y --no-install-recommends "linux-tools-${KVER}" 2>/dev/null \
    || sudo apt-get install -y --no-install-recommends linux-tools-generic
echo -1 | sudo tee /proc/sys/kernel/perf_event_paranoid >/dev/null
echo  0 | sudo tee /proc/sys/kernel/kptr_restrict        >/dev/null
REMOTE
fi

echo "==> Uploading repo..."
rsync -az \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='bench/output' \
    --exclude='build/' \
    -e "ssh ${SSH_OPTS[*]}" \
    "$REPO_ROOT/" "$ADMIN@$VM_IP:~/kvc/"

echo "==> Installing perf_orchestrator..."
ssh "${SSH_OPTS[@]}" "$ADMIN@$VM_IP" \
    "python3 -m pip install --break-system-packages ~/kvc/tools/perf-orchestrator"

echo "==> Running benchmark..."
BENCH_ARGS="--env Azure-$VM_SIZE"
[[ ${#PASSTHROUGH[@]} -gt 0 ]] && BENCH_ARGS+=" $(printf "%q " "${PASSTHROUGH[@]}")"
ssh "${SSH_OPTS[@]}" "$ADMIN@$VM_IP" "cd ~/kvc && python3 bench/main.py $BENCH_ARGS"

echo "==> Downloading results..."
rsync -az \
    -e "ssh ${SSH_OPTS[*]}" \
    "$ADMIN@$VM_IP:~/kvc/bench/output/" \
    "$SCRIPT_DIR/output/"

echo "==> Done. Results in bench/output/"
