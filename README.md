<img src=".github/banner.jpg" alt="gpu.nz examples — ComfyUI, FLUX, Ollama, vLLM and Jupyter on rented GPUs" width="100%">

# gpu.nz examples — run ComfyUI, FLUX, Ollama, vLLM and Jupyter on rented GPUs

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](python/)
[![API](https://img.shields.io/badge/API-REST%20v1-informational.svg)](https://gpu.nz/en/docs/api)
[![Billing](https://img.shields.io/badge/billing-per%20minute-orange.svg)](https://gpu.nz/en/pricing)

**English** | [Русский](#русский)

[gpu.nz](https://gpu.nz) rents cloud GPUs (RTX 3060 to H100 and beyond) by the minute for AI work, with balance top-ups in rubles (SBP) or crypto.
This repository has copy-paste examples that use the public REST API and the `gpunz` CLI: find the cheapest GPU, launch a ready-made app, connect, and stop it again.

> **Safe by default.** Every script that rents a server prints the hourly price first and does nothing without an explicit `--yes`. The read-only scripts and notebook 01 need no API key and spend nothing.

## Examples

| Example | What it does | Recommended GPU | VRAM |
| --- | --- | --- | --- |
| [`python/find_cheapest.py`](python/find_cheapest.py) | Cheapest offers for a minimum VRAM (read-only) | any | any |
| [`python/cost_estimate.py`](python/cost_estimate.py) | Price per hour x minutes (read-only) | any | any |
| [`python/launch_comfyui.py`](python/launch_comfyui.py) / [`cli/comfyui.sh`](cli/comfyui.sh) | ComfyUI for FLUX, SDXL and video | RTX 3090 / 4090 (`rtx-3090-24gb`, `rtx-4090-24gb`) | 12 GB SDXL, 16-24 GB FLUX, 24-48 GB video |
| [`python/launch_ollama.py`](python/launch_ollama.py) / [`cli/ollama.sh`](cli/ollama.sh) | Open WebUI + Ollama chat and API | RTX A4000 / 4060 Ti 16 GB; RTX 3090 for ~30B | 8 GB for 7B, 16 GB for 14B, 24 GB for ~32B (4-bit) |
| [`python/launch_vllm_openai.py`](python/launch_vllm_openai.py) | vLLM with an OpenAI-compatible API, queried with the `openai` client | RTX 3090 / 4090 / L4 / A10 | 24 GB for a 7B model in 16-bit |
| [`python/launch_jupyter.py`](python/launch_jupyter.py) | PyTorch + JupyterLab for training and experiments | RTX 4060 Ti 16 GB or RTX 3090 | 16-24 GB |
| [`cli/cheapest-4090.sh`](cli/cheapest-4090.sh) | Cheapest RTX 4090 offers with `--json` + `jq` (read-only) | RTX 4090 (`rtx-4090-24gb`) | 24 GB |
| [`notebooks/01_find_and_price_gpus.ipynb`](notebooks/01_find_and_price_gpus.ipynb) | List GPUs, prices, VRAM chart (read-only) | any | any |
| [`notebooks/02_launch_and_stop.ipynb`](notebooks/02_launch_and_stop.ipynb) | Guarded launch and cleanup flow | configurable | configurable |

Not sure how much memory you need? Read the [VRAM guide](docs/vram-guide.md): SDXL, FLUX, video and 7B-70B LLMs at 4/8/16-bit.

## Quick start

1. **Install the CLI** (optional but handy):

   ```bash
   # Linux, macOS, WSL
   curl -fsSL https://gpu.nz/install.sh | sh
   ```

   ```powershell
   # Windows PowerShell
   irm https://gpu.nz/install.ps1 | iex
   ```

2. **Get an API key** — create one in the console (Keys page) or run `gpunz login`, then:

   ```bash
   export GPUNZ_API_KEY="gpz_xxx"      # never commit a real key
   ```

   Catalogue calls (GPUs, offers, templates) are public and work without a key.

3. **Try the read-only scripts:**

   ```bash
   pip install -r requirements.txt
   cd python
   python find_cheapest.py --min-vram 24
   python cost_estimate.py --gpu rtx-4090-24gb --minutes 90
   ```

4. **Launch an app** (dry run first, then `--yes`):

   ```bash
   python launch_comfyui.py            # prints the price, rents nothing
   python launch_comfyui.py --yes      # rents, waits, prints SSH and web links
   gpunz stop SERVER_ID                # when you are done (disk kept)
   gpunz destroy SERVER_ID             # or delete everything (ends all billing)
   ```

   Add your SSH public key once with `gpunz ssh-keys add` so you can log in without a password.

### Use the client in your own code

```python
from gpunz_client import GpunzClient

client = GpunzClient()                       # reads GPUNZ_API_KEY from the environment
offer = client.search_offers(gpu="rtx-4090-24gb", num_gpus=1, order="price", limit=1)[0]
print(offer["id"], offer["price"]["on_demand_kop_h"] / 100, "RUB/h")

inst = client.create_instance(offer["id"], "comfyui", disk_gb=100)   # spends money!
inst = client.wait_until_running(inst["id"])
print(inst["ssh"]["command"])
client.destroy_instance(inst["id"])
```

### Call a vLLM server with the OpenAI client

```python
from openai import OpenAI

client = OpenAI(base_url="https://<id>-8000.run.gpu.nz/v1", api_key="<access token>")
print(client.chat.completions.create(
    model="Qwen/Qwen2.5-7B-Instruct",
    messages=[{"role": "user", "content": "Hello!"}],
).choices[0].message.content)
```

`base_url` and the access token come from the server page, as described in the [docs](https://gpu.nz/en/docs).

## What does it cost?

Billing is **per minute** while a server runs: `price per hour / 60 x minutes`. A stopped server costs only its disk; a destroyed one costs nothing. Live prices are at [gpu.nz/pricing](https://gpu.nz/en/pricing) and change with supply, so use `find_cheapest.py` before you launch. Offer prices are for the whole server (divide by the GPU count for a per-card price) and are quoted in rubles; the account is charged in its own currency.

## Layout

```
python/      gpunz_client.py + find_cheapest, cost_estimate, launch_* scripts
cli/         shell recipes using the gpunz CLI (--json + jq)
notebooks/   01 read-only exploration, 02 guarded launch/stop
docs/        vram-guide.md
```

## Links

- API docs: https://gpu.nz/en/docs/api · OpenAPI: https://gpu.nz/api/v1/openapi.json
- Getting started: https://gpu.nz/en/docs · CLI: https://gpu.nz/en/docs/cli
- Templates (ready apps): https://gpu.nz/en/templates · Prices: https://gpu.nz/en/pricing

MIT licensed. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

<a id="русский"></a>

# Русский

**gpu.nz examples — ComfyUI, FLUX, Ollama, vLLM и Jupyter на арендованных GPU**

[gpu.nz](https://gpu.nz) — облачные GPU (от RTX 3060 до H100 и выше) с поминутной оплатой для задач ИИ. Баланс пополняется в рублях (СБП) или криптовалютой.
В репозитории — готовые примеры для публичного REST API и CLI `gpunz`: найти самую дешёвую карту, запустить готовое приложение, подключиться и остановить сервер.

> **Безопасно по умолчанию.** Каждый скрипт, который арендует сервер, сначала печатает цену за час и ничего не делает без явного `--yes`. Скрипты «только чтение» и ноутбук 01 не требуют ключа и ничего не тратят.

## Примеры

| Пример | Что делает | Рекомендуемая GPU | VRAM |
| --- | --- | --- | --- |
| [`python/find_cheapest.py`](python/find_cheapest.py) | Самые дешёвые предложения по минимуму VRAM (чтение) | любая | любой |
| [`python/cost_estimate.py`](python/cost_estimate.py) | Цена за час x минуты (чтение) | любая | любой |
| [`python/launch_comfyui.py`](python/launch_comfyui.py) / [`cli/comfyui.sh`](cli/comfyui.sh) | ComfyUI для FLUX, SDXL и видео | RTX 3090 / 4090 | 12 ГБ SDXL, 16-24 ГБ FLUX, 24-48 ГБ видео |
| [`python/launch_ollama.py`](python/launch_ollama.py) / [`cli/ollama.sh`](cli/ollama.sh) | Open WebUI + Ollama: чат и API | RTX A4000 / 4060 Ti 16 ГБ; RTX 3090 для ~30B | 8 ГБ для 7B, 16 ГБ для 14B, 24 ГБ для ~32B (4 бита) |
| [`python/launch_vllm_openai.py`](python/launch_vllm_openai.py) | vLLM с OpenAI-совместимым API и клиент `openai` | RTX 3090 / 4090 / L4 / A10 | 24 ГБ для модели 7B в 16 бит |
| [`python/launch_jupyter.py`](python/launch_jupyter.py) | PyTorch + JupyterLab для обучения и экспериментов | RTX 4060 Ti 16 ГБ или RTX 3090 | 16-24 ГБ |
| [`cli/cheapest-4090.sh`](cli/cheapest-4090.sh) | Самые дешёвые RTX 4090 через `--json` + `jq` (чтение) | RTX 4090 | 24 ГБ |
| [`notebooks/01_find_and_price_gpus.ipynb`](notebooks/01_find_and_price_gpus.ipynb) | Список GPU, цены, график VRAM (чтение) | любая | любой |
| [`notebooks/02_launch_and_stop.ipynb`](notebooks/02_launch_and_stop.ipynb) | Запуск и остановка с защитным флагом | настраивается | настраивается |

Не знаете, сколько памяти нужно? См. [гайд по VRAM](docs/vram-guide.md) (на английском): SDXL, FLUX, видео и LLM 7B-70B в 4/8/16 бит.

## Быстрый старт

1. **Установите CLI:**

   ```bash
   # Linux, macOS, WSL
   curl -fsSL https://gpu.nz/install.sh | sh
   ```

   ```powershell
   # Windows PowerShell
   irm https://gpu.nz/install.ps1 | iex
   ```

2. **Получите API-ключ** — в консоли («Ключи» → «API-ключи») или командой `gpunz login`:

   ```bash
   export GPUNZ_API_KEY="gpz_xxx"      # настоящий ключ в репозиторий не коммитьте
   ```

   Каталог (GPU, предложения, шаблоны) публичный и работает без ключа.

3. **Попробуйте скрипты только для чтения:**

   ```bash
   pip install -r requirements.txt
   cd python
   python find_cheapest.py --min-vram 24
   python cost_estimate.py --gpu rtx-4090-24gb --minutes 90
   ```

4. **Запустите приложение** (сначала без `--yes`, затем с ним):

   ```bash
   python launch_comfyui.py            # покажет цену, ничего не арендует
   python launch_comfyui.py --yes      # арендует, дождётся запуска, выведет SSH и ссылки
   gpunz stop ID_СЕРВЕРА               # когда закончили (диск сохраняется)
   gpunz destroy ID_СЕРВЕРА            # или удалить всё (оплата прекращается полностью)
   ```

   Один раз добавьте публичный SSH-ключ командой `gpunz ssh-keys add`, чтобы входить без пароля.

## Сколько это стоит

Оплата **поминутная**, пока сервер работает: `цена за час / 60 x минуты`. Остановленный сервер стоит только хранение диска, удалённый — ничего. Актуальные цены — на [gpu.nz/pricing](https://gpu.nz/pricing); они меняются вместе с наличием, поэтому перед запуском выполните `find_cheapest.py`. Цены предложений — за весь сервер (для цены за карту делите на число GPU), в рублях; списание идёт в валюте вашего аккаунта.

## Ссылки

- Документация API: https://gpu.nz/docs/api · OpenAPI: https://gpu.nz/api/v1/openapi.json
- Быстрый старт: https://gpu.nz/docs · CLI: https://gpu.nz/docs/cli
- Шаблоны (готовые приложения): https://gpu.nz/templates · Цены: https://gpu.nz/pricing

Лицензия MIT. См. [CONTRIBUTING.md](CONTRIBUTING.md).
