#!/usr/bin/env python3
"""Estimate what a rental costs: price per hour x minutes. Read-only.

Billing is per minute, so ``cost = price_per_hour / 60 * minutes``. Give the price directly,
or let the script look it up from the public catalogue.

Examples::

    python cost_estimate.py --price-rub-h 33 --minutes 90
    python cost_estimate.py --gpu rtx-4090-24gb --count 2 --minutes 240
    python cost_estimate.py --offer-id OFFER_ID --minutes 45
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from gpunz_client import GpunzClient, GpunzError, estimate_cost_minor, format_money, rub_to_usd


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--price-rub-h", type=float, help="price in rubles per hour (whole server)")
    src.add_argument("--gpu", help="GPU slug: uses the cheapest current per-card price from the catalogue")
    src.add_argument("--offer-id", help="look the hourly price up from this offer")
    p.add_argument("--count", type=int, default=1, help="number of GPUs (used with --gpu)")
    p.add_argument("--minutes", type=float, required=True, help="how long the server runs")
    p.add_argument("--usd-rub", type=float, help="rubles per dollar (only needed for --price-rub-h; otherwise live)")
    args = p.parse_args(argv)

    usd_rub = args.usd_rub
    try:
        client = GpunzClient()
        if args.price_rub_h is not None:
            kop_h = args.price_rub_h * 100
            label = "given price"
        elif args.offer_id:
            offer = client.get_offer(args.offer_id)
            kop_h = offer["price"]["on_demand_kop_h"]
            label = f"offer {offer['id']} ({offer['gpu']['name']} x{offer['gpu']['count']})"
        else:
            body = client.list_gpus()
            usd_rub = usd_rub or body["fx"]["usd_rub"]
            model = next((g for g in client.iter_gpus() if g["slug"] == args.gpu), None)
            if model is None or model["from_kop_h"] is None:
                print(f"error: no current price for GPU {args.gpu!r}", file=sys.stderr)
                return 1
            kop_h = model["from_kop_h"] * args.count
            label = f"{model['name']} x{args.count} (cheapest on-demand per-card price x count)"
        if usd_rub is None:
            usd_rub = client.list_gpus()["fx"]["usd_rub"]
    except GpunzError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Basis: {label}: {format_money(kop_h)}/h\n")
    print(f"{'Runtime':<14}{'RUB':>12}{'USD (approx)':>16}")
    durations = sorted({15.0, 60.0, 240.0, 1440.0, float(args.minutes)})
    for m in durations:
        cost = estimate_cost_minor(kop_h, m)
        usd = rub_to_usd(cost, usd_rub)
        mark = "  <- yours" if m == args.minutes else ""
        print(f"{m:>8g} min  {cost / 100:>12.2f}{(f'{usd:.3f}' if usd is not None else '-'):>16}{mark}")
    print("\nA stopped server costs only its disk. A destroyed one costs nothing. Prices: https://gpu.nz/pricing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
