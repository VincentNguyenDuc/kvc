#!/usr/bin/env bash
# bench/azure_build_image.sh — Bake a managed Azure image with all kvc bench
# dependencies pre-installed so benchmark VMs start instantly.
#
# The image is stored in a persistent resource group (default: kvc-images).
# A temporary resource group is used for the bake VM and deleted afterwards.
# Re-running replaces the image with the same name.
#
# Usage: bench/azure_build_image.sh --location REGION [options]
# Requires: az CLI (logged in), ssh
set -euo pipefail

IMAGE_RG="kvc-images"
IMAGE_NAME="kvc-bench-base"
BAKE_RG="kvc-bake-$(date +%s)"
VM_NAME="kvc-bake"
VM_SIZE=""        # auto-detected from BAKE_SKUS if not set
BASE_IMAGE="Canonical:ubuntu-24_04-lts:server:latest"
ADMIN="bench"
LOCATION=""

# Cheap SKUs tried in order; first one with no capacity restrictions wins.
BAKE_SKUS=("Standard_D2s_v3" "Standard_B2s" "Standard_B2ms" "Standard_D2as_v4" "Standard_D2s_v4")

usage() {
    cat <<'EOF'
Usage: bench/azure_build_image.sh --location REGION [options]

Provisions a temporary VM, installs all kvc benchmark dependencies,
captures a managed image, then tears down the VM. The image persists
in the 'kvc-images' resource group and can be passed to azure.sh.

Options:
  --location REGION     Azure region (required)
  --image-rg NAME       resource group for the image (default: kvc-images)
  --image-name NAME     image name (default: kvc-bench-base)
  --vm-size SIZE        VM size for baking (auto-selected if omitted)
  -h, --help            show this help

After building, run benchmarks with:
  bench/azure.sh --location REGION --image IMAGE_ID [bench/main.py options...]
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --location)   LOCATION="$2";   shift 2 ;;
        --image-rg)   IMAGE_RG="$2";   shift 2 ;;
        --image-name) IMAGE_NAME="$2"; shift 2 ;;
        --vm-size)    VM_SIZE="$2";    shift 2 ;;
        -h|--help)    usage; exit 0 ;;
        *) echo "error: unknown option: $1" >&2; usage; exit 1 ;;
    esac
done

if [[ -z "$LOCATION" ]]; then
    echo "error: --location is required" >&2
    echo "Run 'az account list-locations --query \"[].name\" -o tsv' to list regions." >&2
    exit 1
fi

SSH_OPTS=(-o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15)

# Find the first SKU in BAKE_SKUS that has no capacity restrictions in LOCATION.
find_available_sku() {
    local location="$1"
    for sku in "${BAKE_SKUS[@]}"; do
        local restricted
        restricted=$(az vm list-skus \
            --location "$location" --size "$sku" \
            --query "length([?restrictions[?reasonCode=='NotAvailableForSubscription']])" \
            -o tsv 2>/dev/null) || restricted=1
        if [[ "$restricted" == "0" ]]; then
            echo "$sku"
            return 0
        fi
    done
    return 1
}

cleanup() {
    echo "==> Deleting bake resource group $BAKE_RG (--no-wait)..."
    az group delete --name "$BAKE_RG" --yes --no-wait 2>/dev/null || true
}
trap cleanup EXIT

# ── Image resource group (persistent) ─────────────────────────────────────────
echo "==> Ensuring image resource group '$IMAGE_RG' exists in $LOCATION..."
az group create --name "$IMAGE_RG" --location "$LOCATION" -o none

# ── Bake VM ────────────────────────────────────────────────────────────────────
if [[ -z "$VM_SIZE" ]]; then
    echo "==> Finding an available VM size in $LOCATION..."
    VM_SIZE=$(find_available_sku "$LOCATION") || {
        echo "error: no available VM size found in $LOCATION — use --vm-size to specify one." >&2
        exit 1
    }
fi
echo "==> Creating bake VM ($VM_SIZE in $LOCATION)..."
az group create --name "$BAKE_RG" --location "$LOCATION" -o none
az vm create \
    --resource-group "$BAKE_RG" \
    --name "$VM_NAME" \
    --image "$BASE_IMAGE" \
    --size "$VM_SIZE" \
    --admin-username "$ADMIN" \
    --generate-ssh-keys \
    --public-ip-sku Standard \
    -o none

VM_IP=$(az vm show -g "$BAKE_RG" -n "$VM_NAME" --show-details --query publicIps -o tsv)

echo "==> Waiting for SSH at $VM_IP..."
until ssh "${SSH_OPTS[@]}" "$ADMIN@$VM_IP" true 2>/dev/null; do sleep 5; done

# ── Install dependencies ───────────────────────────────────────────────────────
echo "==> Installing dependencies..."
ssh "${SSH_OPTS[@]}" "$ADMIN@$VM_IP" bash -s <<'REMOTE'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    build-essential python3 python3-pip \
    util-linux perl libc6-dbg \
    linux-tools-common

KVER=$(uname -r)
sudo apt-get install -y --no-install-recommends "linux-tools-${KVER}" 2>/dev/null \
    || sudo apt-get install -y --no-install-recommends linux-tools-generic

# Persist perf settings so they survive reboot into a bench VM
cat <<'SYSCTL' | sudo tee /etc/sysctl.d/99-perf.conf
kernel.perf_event_paranoid = -1
kernel.kptr_restrict = 0
SYSCTL

echo "==> Deprovisioning..."
sudo waagent -deprovision+user -force
REMOTE

# ── Capture image ──────────────────────────────────────────────────────────────
echo "==> Deallocating and generalizing bake VM..."
az vm deallocate --resource-group "$BAKE_RG" --name "$VM_NAME"
az vm generalize  --resource-group "$BAKE_RG" --name "$VM_NAME"

VM_ID=$(az vm show --resource-group "$BAKE_RG" --name "$VM_NAME" --query id -o tsv)

echo "==> Replacing image '$IMAGE_NAME' in '$IMAGE_RG'..."
az image delete --resource-group "$IMAGE_RG" --name "$IMAGE_NAME" 2>/dev/null || true
az image create \
    --resource-group "$IMAGE_RG" \
    --name "$IMAGE_NAME" \
    --source "$VM_ID" \
    --hyper-v-generation V2 \
    --location "$LOCATION" \
    -o none

IMAGE_ID=$(az image show --resource-group "$IMAGE_RG" --name "$IMAGE_NAME" --query id -o tsv)

echo ""
echo "Image ready: $IMAGE_ID"
echo ""
echo "Run benchmarks with:"
echo "  bench/azure.sh --location $LOCATION --image \"$IMAGE_ID\" [bench/main.py options...]"
