# Contributing

Thanks for helping! Small, focused pull requests are easiest to review.

## Ground rules

- **Never commit secrets.** Use the `GPUNZ_API_KEY` environment variable and placeholders such as `gpz_xxx`.
- **Safe by default.** Any script that rents a server must print the hourly price first, do nothing without an explicit `--yes` (or an equivalent flag), and end with stop / destroy instructions.
- **Match the API.** Field names, parameters and headers must follow the OpenAPI spec at https://gpu.nz/api/v1/openapi.json. Use exact GPU and template slugs from `GET /gpus` and `GET /templates`.
- Python 3.9+, `requests` only for the core client, type hints and docstrings, English comments.

## Checks (same as CI)

```bash
python -m py_compile python/*.py
for f in notebooks/*.ipynb; do python -m json.tool "$f" > /dev/null; done
for f in cli/*.sh; do bash -n "$f"; done
```

Read-only scripts (`find_cheapest.py`, `cost_estimate.py`, notebook 01) can be run against the live API without a key.
Please do not add examples that need paid resources just to run their tests.

## Adding an example

1. Add a script under `python/` (reuse `launch_common.py`) or a recipe under `cli/`.
2. Add a row to the table in `README.md` (English and Russian) with the GPU recommendation and VRAM.
3. Put the VRAM reasoning in `docs/vram-guide.md` if it is new.
