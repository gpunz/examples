#!/usr/bin/env python3
"""Launch Open WebUI + Ollama (your own ChatGPT-style chat and an API) on a rented GPU.

Dry run by default: prints the price and exits. Add ``--yes`` to rent.

    python launch_ollama.py                  # quote only
    python launch_ollama.py --min-vram 16 --yes

Rule of thumb: 8 GB for 7-8B models (4-bit), 16 GB for 14B, 24 GB for ~32B.
See docs/vram-guide.md. Needs GPUNZ_API_KEY only for ``--yes``.
"""

from __future__ import annotations

import sys

from gpunz_client import Json
from launch_common import LaunchSpec, run


def after_launch(inst: Json) -> None:
    print("\nNext steps:")
    print("  1. Open the Open WebUI link (port 7500) and pull a model from the chat, or over SSH:  ollama pull qwen3:8b")
    print("  2. The Ollama API (port 11434) has a protected link on the server page. Call it with the access token:")
    print('       curl "$OLLAMA_URL/api/chat" -H "Authorization: Bearer $ACCESS_TOKEN" \\')
    print('         -d \'{"model": "qwen3:8b", "stream": false, "messages": [{"role": "user", "content": "Hello"}]}\'')
    print("     $OLLAMA_URL is the Ollama API link from the server page; $ACCESS_TOKEN is the token shown there.")
    print("     The /v1 route is OpenAI-compatible, so any OpenAI SDK works with base_url=$OLLAMA_URL/v1.")


SPEC = LaunchSpec(
    title="Open WebUI + Ollama on a rented GPU",
    template="ollama",
    default_disk_gb=60,
    default_min_vram_gb=16,
    name_prefix="ollama",
    default_gpus="rtx-4060-ti-16gb,rtx-5060-ti-16gb,rtx-4070s-ti-16gb,rtx-a4000-16gb,rtx-5080-16gb,rtx-3090-24gb,rtx-4090-24gb",
    after_launch=after_launch,
)

if __name__ == "__main__":
    sys.exit(run(SPEC))
