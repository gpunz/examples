#!/usr/bin/env python3
"""Launch ComfyUI (FLUX, SDXL, Wan video) on the cheapest suitable GPU.

Dry run by default: prints the price and exits. Add ``--yes`` to rent.

    python launch_comfyui.py                 # quote only
    python launch_comfyui.py --min-vram 24 --yes

VRAM: SDXL runs on 12 GB, FLUX fp8 on 16-24 GB, video models want 24-48 GB.
See docs/vram-guide.md. Needs GPUNZ_API_KEY only for ``--yes``.
"""

from __future__ import annotations

import sys

from gpunz_client import Json
from launch_common import LaunchSpec, run


def after_launch(inst: Json) -> None:
    print("\nNext steps:")
    print("  1. Open the URL labelled 8188 above: that is the ComfyUI interface (the link carries an access token, do not share it).")
    print("  2. Download models into the ComfyUI models folder over SSH, e.g. with `huggingface-cli download`.")
    print("  3. Copy results back with scp/rsync BEFORE you destroy the server.")


SPEC = LaunchSpec(
    title="ComfyUI on a rented GPU",
    template="comfyui",
    default_disk_gb=100,
    default_min_vram_gb=24,
    name_prefix="comfyui",
    default_gpus="rtx-3090-24gb,rtx-4090-24gb,rtx-5090-32gb",
    after_launch=after_launch,
)

if __name__ == "__main__":
    sys.exit(run(SPEC))
