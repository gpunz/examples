#!/usr/bin/env bash
# Launch ComfyUI on the cheapest suitable GPU with the gpunz CLI.
#
#   ./comfyui.sh          # dry run: shows the offer and its price, rents nothing
#   ./comfyui.sh --yes    # really rents it (billed per minute until you stop/destroy)
#
# Tunables (environment): MIN_VRAM (GB, default 24), DISK_GB (default 100),
#                         GPUS (comma-separated model slugs).
# Requires: gpunz (https://gpu.nz/docs/cli), jq, and GPUNZ_API_KEY or `gpunz login` for --yes.
set -euo pipefail

MIN_VRAM="${MIN_VRAM:-24}"
DISK_GB="${DISK_GB:-100}"
GPUS="${GPUS:-rtx-3090-24gb,rtx-4090-24gb,rtx-5090-32gb}"
TEMPLATE="comfyui"

command -v gpunz >/dev/null || { echo "gpunz not found: curl -fsSL https://gpu.nz/install.sh | sh" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

# Public, read-only: cheapest single-GPU offer with enough VRAM.
offer_json="$(gpunz --json search --gpu "$GPUS" --num-gpus 1 --min-vram "$MIN_VRAM" \
  --min-reliability 0.95 --min-disk "$DISK_GB" --order price --limit 1)"
offer_id="$(jq -r '.data[0].id // empty' <<<"$offer_json")"
[ -n "$offer_id" ] || { echo "No offer matches. Lower MIN_VRAM or widen GPUS." >&2; exit 1; }

jq -r '.data[0] | "Offer \(.id): \(.gpu.name) x\(.gpu.count), \(.gpu.vram_gb) GB, \(.country // "?")\nPrice: \(.price.on_demand_kop_h / 100) RUB/h  (\(.price.on_demand_kop_h / 6000 * 100 | round / 100) RUB/min, market price)"' <<<"$offer_json"

if [ "${1:-}" != "--yes" ]; then
  echo
  echo "DRY RUN: nothing rented. Re-run with --yes to rent."
  exit 0
fi

created="$(gpunz --json create "$offer_id" --template "$TEMPLATE" --disk "$DISK_GB" --name comfyui-example)"
id="$(jq -r '.id' <<<"$created")"
echo "Created $id, billed $(jq -r '.price.running_kop_h' <<<"$created") minor units/h ($(jq -r '.currency' <<<"$created"))"

echo -n "Waiting for it to start"
until [ "$(gpunz --json show "$id" | jq -r '.status')" = "running" ]; do
  status="$(gpunz --json show "$id" | jq -r '.status')"
  case "$status" in failed|destroyed|destroying|stopped|outbid) echo; echo "Instance is $status. See: gpunz logs $id" >&2; exit 1 ;; esac
  echo -n "."; sleep 10
done
echo

gpunz --json show "$id" | jq -r '"SSH: \(.ssh.command // "pending")", (.urls[]? | "URL [\(.label)]: \(.url // "not ready yet")")'
echo "Open the URL labelled 8188 for ComfyUI."
echo
echo "When done:  gpunz stop $id      # keeps the disk, tiny disk-only fee"
echo "            gpunz destroy $id   # deletes everything, ends all billing"
