# VRAM guide: which GPU do you need?

VRAM (GPU memory) is the one number that decides whether a model runs at all. Speed is secondary:
a slower card with enough memory beats a faster card that runs out of it.

> These are rule-of-thumb figures for planning, not guarantees. Context length, batch size, framework
> and quantization format all move the numbers by a few GB. Start with the smaller card, watch
> `nvidia-smi`, and move up only if you run out of memory. Billing is per minute, so trying is cheap.

## The formula

```
weights  ≈ parameters × bytes per parameter
VRAM     ≈ weights × 1.2  (+ KV cache for long contexts / big batches)
```

| Precision | Bytes per parameter | Notes |
| --- | --- | --- |
| 16-bit (FP16 / BF16) | 2.0 | Reference quality. |
| 8-bit (INT8 / FP8) | 1.0 | Near-lossless for most uses. |
| 4-bit (Q4 / AWQ / GPTQ / NF4) | about 0.5-0.6 | Small quality loss; the default for Ollama / GGUF. |

## Language models (inference)

| Model size | 16-bit | 8-bit | 4-bit | Cheapest comfortable card |
| --- | --- | --- | --- | --- |
| 7-8B | ~16 GB weights, plan 24 GB | ~9 GB, plan 12 GB | ~5 GB, plan 8 GB | 4-bit: RTX 3060 12 GB; 16-bit: RTX 3090 / 4090 24 GB |
| 13-14B | ~28 GB, plan 40 GB | ~15 GB, plan 24 GB | ~8 GB, plan 12 GB | 4-bit: RTX 3060 12 GB / A4000 16 GB; 8-bit: RTX 3090 24 GB |
| 30-34B | ~68 GB, plan 80 GB | ~35 GB, plan 48 GB | ~19 GB, plan 24 GB | 4-bit: RTX 3090 / 4090 24 GB; 8-bit: A6000 / L40S 48 GB |
| 70B | ~140 GB, plan 2 x 80 GB | ~75 GB, plan 80+ GB | ~40 GB, plan 48 GB | 4-bit: A6000 / L40S 48 GB; 8-bit: A100 / H100 80 GB |
| 120B MoE (e.g. GPT-OSS 120B) | not needed | n/a | ~65 GB, plan 80 GB | A100 / H100 80 GB |

Long contexts add KV cache on top: a few GB for 8k tokens, tens of GB for 128k. In vLLM cap it with
`--max-model-len 8192` if memory is tight.

## Image generation

| Model | Minimum | Comfortable | Notes |
| --- | --- | --- | --- |
| Stable Diffusion 1.5 | 4 GB | 8 GB | Cheapest cards are enough. |
| SDXL | 8 GB | 12-16 GB | Refiner, ControlNet and upscalers push toward 16 GB. |
| FLUX.1 [dev] / [schnell], FP8 or GGUF Q4-Q8 | 12-16 GB | 24 GB | The usual choice: RTX 3090 / 4090. |
| FLUX.1, full BF16 | 24 GB with offloading | 40-48 GB | Text encoders add about 10 GB. |

## Video generation

| Model | Minimum | Comfortable |
| --- | --- | --- |
| Wan 2.x small (about 1-5B) | 8-12 GB | 16 GB |
| Wan 2.x 14B, FP8 | 16-24 GB with offloading | 48 GB |
| HunyuanVideo (13B), FP8 | 24 GB with offloading | 48-80 GB |
| LTX-Video | 12 GB | 24 GB |

Resolution and clip length scale memory (and time) quickly; start at low resolution.

## Training and fine-tuning

| Task | Typical VRAM |
| --- | --- |
| SDXL LoRA | 12-16 GB |
| FLUX LoRA | 24 GB (16 GB with aggressive tricks) |
| QLoRA (4-bit base) 7-8B | 16-24 GB |
| QLoRA 13-14B | 24 GB |
| QLoRA 70B | 48-80 GB |
| Full fine-tune 7B (16-bit, Adam) | 100+ GB (about 16 bytes per parameter: use LoRA or several GPUs) |

## Which card to pick

| You want | Pick | Model slug |
| --- | --- | --- |
| Cheapest experiments, SDXL, 7B at 4-bit | RTX 3060 12 GB | `rtx-3060-12gb` |
| 14B models, small LoRAs | RTX A4000 / RTX 4060 Ti 16 GB | `rtx-a4000-16gb`, `rtx-4060-ti-16gb` |
| FLUX, 7B at 16-bit, 30B at 4-bit (best value) | RTX 3090 / RTX 4090 24 GB | `rtx-3090-24gb`, `rtx-4090-24gb` |
| Faster 24-32 GB work | RTX 5090 32 GB | `rtx-5090-32gb` |
| 70B at 4-bit, big image / video pipelines | L40S / RTX A6000 48 GB | `l40s-48gb`, `rtx-a6000-48gb` |
| 70B at 8-bit, 120B MoE, serious training | A100 / H100 80 GB | `a100-pcie-80gb`, `h100-sxm-80gb` |
| Multi-GPU or the largest models | H200 141 GB and up | `h200-141gb` |

Find the live price of any of these:

```bash
python python/find_cheapest.py --gpu rtx-4090-24gb
```

or browse https://gpu.nz/pricing. Prices change with supply.

## Tips to save VRAM

- Use a quantized build (GGUF / AWQ / FP8) of the model: halves or quarters the weights.
- Lower the context length and batch size.
- In ComfyUI use FP8 weights and "low VRAM" / tiled VAE options.
- Offloading to system RAM works but is slow; a bigger card is often cheaper per finished result.
