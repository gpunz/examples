#!/usr/bin/env python3
"""Find the cheapest rentable offers for a minimum amount of VRAM. Read-only and safe.

Uses only public endpoints, so no API key is needed and nothing is rented or charged.

Examples::

    python find_cheapest.py --min-vram 24
    python find_cheapest.py --gpu rtx-4090-24gb,rtx-3090-24gb --limit 10
    python find_cheapest.py --min-vram 80 --type interruptible --country DE,NL
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from gpunz_client import GpunzClient, GpunzError, format_money, per_gpu_kop_h, rub_to_usd


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--min-vram", type=float, default=24, help="minimum VRAM per GPU, GB (default 24)")
    p.add_argument("--gpu", help="comma-separated exact GPU slugs, e.g. rtx-4090-24gb (list: gpunz gpus)")
    p.add_argument("--num-gpus", default="1", help="GPUs per server: 1, 2, 4 or 8, comma-separated (default 1)")
    p.add_argument("--type", choices=["on_demand", "interruptible"], default="on_demand")
    p.add_argument("--country", help="ISO-2 country codes, comma-separated")
    p.add_argument("--min-reliability", type=float, default=0.95)
    p.add_argument("--verified", action="store_true", help="verified datacenters only")
    p.add_argument("--min-disk", type=float, help="minimum disk, GB")
    p.add_argument("--limit", type=int, default=5)
    args = p.parse_args(argv)

    client = GpunzClient()
    try:
        page = client.search_offers_page(
            gpu=args.gpu,
            num_gpus=args.num_gpus,
            type=args.type,
            country=args.country,
            min_reliability=args.min_reliability,
            min_vram_gb=args.min_vram,
            min_disk_gb=args.min_disk,
            verified=True if args.verified else None,
            order="price",
            limit=max(1, min(200, args.limit)),
        )
    except GpunzError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    offers = page["data"]
    usd_rub = page.get("fx", {}).get("usd_rub")
    if not offers:
        print("No offers match these filters right now. Try a lower --min-vram or --min-reliability.")
        return 0

    key = "interruptible_kop_h" if args.type == "interruptible" else "on_demand_kop_h"
    print(f"Cheapest {args.type} offers with >= {args.min_vram:g} GB VRAM (market prices, whole server):\n")
    header = f"{'OFFER ID':<14}{'GPU':<22}{'xN':>3}{'VRAM':>6}{'CTRY':>6}{'RELIAB':>8}{'RUB/h':>10}{'USD/h':>9}{'RUB/GPU/h':>11}"
    print(header)
    print("-" * len(header))
    for o in offers:
        kop_h = o["price"][key]
        if kop_h is None:
            continue
        usd = rub_to_usd(kop_h, usd_rub)
        gpu_h = per_gpu_kop_h(o, args.type == "interruptible")
        rel = o.get("reliability")
        print(
            f"{o['id']:<14}{o['gpu']['name'][:21]:<22}{o['gpu']['count']:>3}{o['gpu']['vram_gb']:>6}"
            f"{(o.get('country') or '-'):>6}{(f'{rel * 100:.1f}%' if rel else '-'):>8}"
            f"{kop_h / 100:>10.2f}{(f'{usd:.3f}' if usd else '-'):>9}{(gpu_h or 0) / 100:>11.2f}"
        )
    best = offers[0]
    best_kop = best["price"][key] or 0
    print(f"\nCheapest: {best['id']} at {format_money(best_kop)}/h = {format_money(best_kop / 60)}/min.")
    print(f"Rent it with:  gpunz create {best['id']} --template SLUG   # see: gpunz templates")
    print("Prices change with supply; see https://gpu.nz/pricing. Nothing was rented.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
