#!/usr/bin/env bash
# Read-only: list the cheapest RTX 4090 offers right now. No API key, nothing is rented.
#
#   ./cheapest-4090.sh [COUNT]      # COUNT defaults to 5
set -euo pipefail

COUNT="${1:-5}"
command -v gpunz >/dev/null || { echo "gpunz not found: curl -fsSL https://gpu.nz/install.sh | sh" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

gpunz --json search --gpu rtx-4090-24gb --num-gpus 1 --order price --limit "$COUNT" |
  jq -r '
    ["OFFER", "COUNTRY", "RUB/H", "RELIABILITY"],
    (.data[] | [.id, (.country // "-"), (.price.on_demand_kop_h / 100), (.reliability // "-")])
    | @tsv' | column -t

echo
echo "Rent one:  gpunz create OFFER_ID --template comfyui --disk 100"
echo "Prices move with supply: https://gpu.nz/pricing"
