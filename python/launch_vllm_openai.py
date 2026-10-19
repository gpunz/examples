#!/usr/bin/env python3
"""Launch vLLM (OpenAI-compatible API) on a rented GPU, then talk to it with the OpenAI client.

Two modes:

1. Rent (dry run by default, ``--yes`` to really rent)::

       python launch_vllm_openai.py                 # quote only
       python launch_vllm_openai.py --min-vram 24 --yes

2. Query a running endpoint (no renting, needs ``pip install openai``)::

       export VLLM_BASE_URL="https://<id>-8000.run.gpu.nz/v1"   # from the server page
       export VLLM_API_KEY="<access token from the server page>"
       python launch_vllm_openai.py --ask "Write a haiku about GPUs"

The template serves Qwen/Qwen2.5-7B-Instruct on port 8000 by default and uses the rental's
access token as the API key. The first start downloads and compiles the model, so the API can
take a few minutes longer than SSH. A 7B model in 16-bit needs about 24 GB of VRAM.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from gpunz_client import Json
from launch_common import LaunchSpec, run

DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"


def extend_parser(p: argparse.ArgumentParser) -> None:
    p.add_argument("--ask", metavar="PROMPT", help="send this prompt to VLLM_BASE_URL instead of renting")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"model name for --ask (default {DEFAULT_MODEL})")


def ask(args: argparse.Namespace) -> Optional[int]:
    """Talk to a running vLLM endpoint with the official OpenAI client."""
    if not args.ask:
        return None
    base_url = os.environ.get("VLLM_BASE_URL")
    api_key = os.environ.get("VLLM_API_KEY")
    if not base_url or not api_key:
        print("error: set VLLM_BASE_URL (ends with /v1) and VLLM_API_KEY (the access token) first.", file=sys.stderr)
        return 2
    try:
        from openai import OpenAI  # imported lazily: only needed for this mode
    except ImportError:
        print("error: pip install openai", file=sys.stderr)
        return 2
    client = OpenAI(base_url=base_url, api_key=api_key)
    reply = client.chat.completions.create(
        model=args.model,
        messages=[{"role": "user", "content": args.ask}],
        max_tokens=256,
    )
    print(reply.choices[0].message.content)
    return 0


def after_launch(inst: Json) -> None:
    print("\nNext steps:")
    print("  1. Wait until the server page says the API is ready (the model is downloaded on first start).")
    print("  2. Take the link for port 8000 from the server page: https://<id>-8000.run.gpu.nz")
    print("     and the access token shown there. Then:")
    print('       export VLLM_BASE_URL="https://<id>-8000.run.gpu.nz/v1"')
    print('       export VLLM_API_KEY="<access token>"')
    print('       python launch_vllm_openai.py --ask "Hello!"')
    print("  Or in your own code:")
    print("       from openai import OpenAI")
    print('       client = OpenAI(base_url="https://<id>-8000.run.gpu.nz/v1", api_key="<access token>")')
    print(f'       client.chat.completions.create(model="{DEFAULT_MODEL}", messages=[...])')
    print("  To serve another model, SSH in and run:  vllm serve <model> --port 8000 --api-key <token> --max-model-len 8192")


SPEC = LaunchSpec(
    title="vLLM (OpenAI-compatible API) on a rented GPU",
    template="vllm",
    default_disk_gb=100,
    default_min_vram_gb=24,
    name_prefix="vllm",
    default_gpus="rtx-3090-24gb,rtx-4090-24gb,rtx-5090-32gb,rtx-a5000-24gb,l4-24gb,a10-24gb,l40s-48gb",
    after_launch=after_launch,
    extend_parser=extend_parser,
    early_exit=ask,
)

if __name__ == "__main__":
    sys.exit(run(SPEC))
