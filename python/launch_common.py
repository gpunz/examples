"""Shared flow for the ``launch_*.py`` examples.

Every launch script does the same safe sequence:

1. find the cheapest suitable offer (public, read-only call);
2. print what it would cost per hour and per minute;
3. **stop there unless ``--yes`` was passed**;
4. with ``--yes``: rent it, wait until it is running, print how to connect;
5. always print how to stop or destroy the instance.

Billing runs while the instance is running. Stop it when you are done.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional

from gpunz_client import (
    ENV_API_KEY,
    GpunzClient,
    GpunzError,
    InstanceStateError,
    Json,
    connection_info,
    format_money,
    rub_to_usd,
)


@dataclass
class LaunchSpec:
    """Describes one example: which template to run and sensible defaults."""

    title: str
    template: str
    default_disk_gb: int
    default_min_vram_gb: int
    name_prefix: str
    default_gpus: str = ""
    after_launch: Optional[Callable[[Json], None]] = None
    extend_parser: Optional[Callable[[argparse.ArgumentParser], None]] = None
    early_exit: Optional[Callable[[argparse.Namespace], Optional[int]]] = None


def build_parser(spec: LaunchSpec) -> argparse.ArgumentParser:
    """Create the CLI parser shared by all launch scripts."""
    p = argparse.ArgumentParser(
        description=f"{spec.title}. Prints the price first; rents only with --yes.",
    )
    p.add_argument("--yes", action="store_true", help="really rent the server (spends money while it runs)")
    p.add_argument("--offer-id", help="rent this exact offer instead of the cheapest match")
    p.add_argument(
        "--gpu",
        default=spec.default_gpus or None,
        help="comma-separated GPU model slugs (default: %(default)s); use 'any' for no restriction",
    )
    p.add_argument("--min-vram", type=float, default=spec.default_min_vram_gb, help="minimum VRAM per GPU, GB")
    p.add_argument("--disk", type=int, help="disk size, GB (default: the template's recommended size)")
    p.add_argument("--type", choices=["on_demand", "interruptible"], default="on_demand")
    p.add_argument("--country", help="ISO-2 country codes, comma-separated, e.g. DE,NL")
    p.add_argument("--min-reliability", type=float, default=0.95, help="0..1 (default 0.95)")
    p.add_argument("--max-price-rub", type=float, help="cap in rubles per hour for the whole server")
    p.add_argument("--name", help="instance name (max 60 chars)")
    p.add_argument("--timeout-min", type=float, default=20.0, help="how long to wait for the server to be ready")
    if spec.extend_parser:
        spec.extend_parser(p)
    return p


def print_cleanup(instance_id: str) -> None:
    """Tell the user how to stop billing. Printed at the end of every rental."""
    print("\n--- When you are done ---")
    print("Stop (GPU billing ends, the disk is kept and still billed a little):")
    print(f"  gpunz stop {instance_id}")
    print(f'  python -c "from gpunz_client import GpunzClient; GpunzClient().stop_instance(\'{instance_id}\')"')
    print("Destroy (deletes the disk and its data, ends all billing):")
    print(f"  gpunz destroy {instance_id}")
    print(f'  python -c "from gpunz_client import GpunzClient; GpunzClient().destroy_instance(\'{instance_id}\')"')


def _pick_offer(client: GpunzClient, spec: LaunchSpec, args: argparse.Namespace, disk_gb: int) -> Optional[Json]:
    if args.offer_id:
        return client.get_offer(args.offer_id)
    offers = client.search_offers(
        gpu=None if args.gpu == "any" else args.gpu,
        num_gpus=1,
        type=args.type,
        country=args.country,
        min_reliability=args.min_reliability,
        min_vram_gb=args.min_vram,
        min_disk_gb=disk_gb,
        max_price_kop_h=int(args.max_price_rub * 100) if args.max_price_rub else None,
        order="price",
        limit=5,
    )
    for offer in offers:
        price = offer["price"]["interruptible_kop_h" if args.type == "interruptible" else "on_demand_kop_h"]
        if offer.get("available", True) and price is not None:
            return offer
    return None


def _print_quote(offer: Json, args: argparse.Namespace, disk_gb: int, usd_rub: Optional[float]) -> int:
    """Print the offer and its price; return the hourly price in kopecks."""
    key = "interruptible_kop_h" if args.type == "interruptible" else "on_demand_kop_h"
    kop_h = offer["price"][key]
    gpu = offer["gpu"]
    usd = rub_to_usd(kop_h, usd_rub)
    print(f"Offer      : {offer['id']}  ({gpu['name']} x{gpu['count']}, {gpu['vram_gb']} GB VRAM each)")
    print(f"Location   : {offer.get('country') or '?'}   reliability: {offer.get('reliability')}")
    print(f"Disk       : {disk_gb} GB")
    usd_part = f"  (~{usd:.3f} USD/h)" if usd is not None else ""
    print(f"Price      : {format_money(kop_h)}/h{usd_part}  [{args.type}, whole server, market price]")
    print(f"Per minute : {format_money(kop_h / 60)}  |  1 hour: {format_money(kop_h)}  |  24 hours: {format_money(kop_h * 24)}")
    print("Note       : the market price is in rubles; your account is charged in its own currency.")
    return int(kop_h)


def run(spec: LaunchSpec, argv: Optional[List[str]] = None) -> int:
    """Entry point used by the ``launch_*.py`` scripts. Returns a process exit code."""
    args = build_parser(spec).parse_args(argv)
    if spec.early_exit:
        code = spec.early_exit(args)
        if code is not None:
            return code

    client = GpunzClient()
    try:
        template = client.get_template(spec.template)
        disk_gb = args.disk or template.get("recommended_disk_gb") or spec.default_disk_gb
        if disk_gb < template.get("min_disk_gb", 10):
            print(f"error: --disk {disk_gb} is below the template minimum ({template['min_disk_gb']} GB)", file=sys.stderr)
            return 2
        print(f"== {spec.title} ==")
        print(f"Template   : {template['slug']} ({template['name']})")
        offer = _pick_offer(client, spec, args, disk_gb)
        if offer is None:
            print("No available offer matches. Relax --min-vram / --min-reliability / --max-price-rub.")
            return 1
        fx = client.list_gpus().get("fx", {}).get("usd_rub")
        _print_quote(offer, args, disk_gb, fx)
    except GpunzError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not args.yes:
        print("\nDRY RUN: nothing was rented and nothing was charged.")
        print("Re-run with --yes to rent this server. You pay per minute until you stop or destroy it.")
        return 0

    if not client.api_key:
        print(f"error: renting needs an API key. Set {ENV_API_KEY}=gpz_xxx (see README).", file=sys.stderr)
        return 3

    name = (args.name or f"{spec.name_prefix}-example")[:60]
    instance_id: Optional[str] = None
    try:
        inst = client.create_instance(offer["id"], spec.template, disk_gb, name=name, type=args.type)
        instance_id = inst["id"]
        price = inst.get("price", {})
        print(f"\nCreated instance {instance_id}. Billed price: {format_money(price.get('running_kop_h', 0), inst.get('currency', 'RUB'))}/h")
        print("Waiting for it to start (the first start downloads the image, this can take several minutes)...")
        last: List[str] = []

        def show(i: Json) -> None:
            status = i.get("status", "?")
            if not last or last[-1] != status:
                last.append(status)
                print(f"  status: {status}")

        inst = client.wait_until_running(instance_id, timeout_s=args.timeout_min * 60, on_update=show)
    except KeyboardInterrupt:
        print("\nInterrupted. The instance may still be running and billing!", file=sys.stderr)
        if instance_id:
            print_cleanup(instance_id)
        return 130
    except (GpunzError, TimeoutError, InstanceStateError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        if isinstance(exc, GpunzError) and exc.code == "insufficient_funds":
            print(f"details: {exc.details}", file=sys.stderr)
        if instance_id:
            print_cleanup(instance_id)
        return 1

    print("\nRunning. Connection info:")
    info = connection_info(inst)
    print(f"  SSH : {info['ssh_command']}")
    for u in info["urls"]:
        print(f"  URL : [{u['label']}] {u['url']}")
    print("  (the SSH root password is in the instance JSON / on the server page; add an SSH key to avoid it)")
    if spec.after_launch:
        spec.after_launch(inst)
    print_cleanup(instance_id)
    return 0
