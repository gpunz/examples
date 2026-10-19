#!/usr/bin/env python3
"""Launch PyTorch + JupyterLab on a rented GPU.

Dry run by default: prints the price and exits. Add ``--yes`` to rent.

    python launch_jupyter.py                 # quote only
    python launch_jupyter.py --min-vram 16 --yes

Good for training, fine-tuning and experiments. Needs GPUNZ_API_KEY only for ``--yes``.
"""

from __future__ import annotations

import sys

from gpunz_client import Json
from launch_common import LaunchSpec, run


def after_launch(inst: Json) -> None:
    print("\nNext steps:")
    print("  1. Open the Jupyter link listed above (it carries an access token, do not share it).")
    print("     Jupyter uses HTTPS with the server's own certificate, so the browser may warn: that is expected.")
    print("  2. Check the GPU in a notebook cell:  import torch; print(torch.cuda.get_device_name(0))")
    print("  3. Save checkpoints and results to your machine (scp/rsync) before destroying the server.")


SPEC = LaunchSpec(
    title="PyTorch + JupyterLab on a rented GPU",
    template="pytorch",
    default_disk_gb=50,
    default_min_vram_gb=16,
    name_prefix="jupyter",
    default_gpus="rtx-4060-ti-16gb,rtx-5060-ti-16gb,rtx-4070s-ti-16gb,rtx-a4000-16gb,rtx-5080-16gb,rtx-3090-24gb,rtx-4090-24gb",
    after_launch=after_launch,
)

if __name__ == "__main__":
    sys.exit(run(SPEC))
