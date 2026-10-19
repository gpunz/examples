"""A tiny, dependency-light Python client for the gpu.nz REST API (v1).

Only ``requests`` is required. Every method maps one-to-one to an endpoint of the
public OpenAPI spec (https://gpu.nz/api/v1/openapi.json).

Conventions of the API worth knowing:

* Auth: ``Authorization: Bearer gpz_...``. Catalog endpoints (``/gpus``,
  ``/offers``, ``/templates``) are public and work without a key.
* Offer prices are *market prices in rubles*, in kopecks per hour (``*_kop_h``),
  for the **whole server** (all GPUs of the offer).
* Instance prices and costs are in the *account's* currency (``RUB`` or ``USD``);
  the minor unit is a kopeck for RUB and 1/10 000 of a dollar for USD.
* Lists are paged with ``limit`` (1-200) and ``cursor`` (``next_cursor``).

Example (read-only, no key needed)::

    from gpunz_client import GpunzClient

    client = GpunzClient()
    for offer in client.search_offers(gpu="rtx-4090-24gb", num_gpus=1, limit=3):
        print(offer["id"], offer["price"]["on_demand_kop_h"] / 100, "RUB/h")
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Union

import requests

DEFAULT_BASE_URL = "https://gpu.nz/api/v1"
ENV_API_KEY = "GPUNZ_API_KEY"
ENV_API_URL = "GPUNZ_API_URL"

Json = Dict[str, Any]
StrOrList = Union[str, Iterable[str]]

# Instance states after which waiting for "running" can never succeed.
_DEAD_STATES = frozenset({"failed", "destroying", "destroyed", "stopping", "stopped", "outbid"})


class GpunzError(Exception):
    """An API error: stable ``code``, human ``message`` and optional ``details``."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        code: Optional[str] = None,
        details: Optional[Json] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.details = details or {}

    def __str__(self) -> str:
        parts = [self.message]
        if self.code:
            parts.append(f"[{self.code}]")
        if self.status:
            parts.append(f"(HTTP {self.status})")
        return " ".join(parts)


class AuthRequiredError(GpunzError):
    """Raised before sending a request that needs an API key when none is set."""


class InstanceStateError(GpunzError):
    """Raised while waiting when an instance reaches a state it cannot recover from."""


def _csv(value: Optional[Union[StrOrList, int]]) -> Optional[str]:
    """Turn ``"a"``, ``["a", "b"]`` or ``2`` into the comma-separated form the API expects."""
    if value is None:
        return None
    if isinstance(value, (str, int)):
        return str(value)
    return ",".join(str(v) for v in value)


# --------------------------------------------------------------------------- money


def kop_to_rub(kop: Union[int, float]) -> float:
    """Kopecks -> rubles. (For USD accounts use :func:`format_money`: its minor unit is 1/10 000 $.)"""
    return kop / 100.0


def format_money(minor: Union[int, float], currency: str = "RUB") -> str:
    """Format an amount in minor units, e.g. ``format_money(2650)`` -> ``"26.50 RUB"``.

    For ``USD`` accounts the minor unit is 1/10 000 of a dollar.
    """
    if currency == "USD":
        return f"{minor / 10_000:.4f} USD"
    return f"{minor / 100:.2f} RUB"


def rub_to_usd(kop: Union[int, float], usd_rub: Optional[float]) -> Optional[float]:
    """Convert kopecks to dollars with the ``fx.usd_rub`` rate from ``/gpus`` or ``/offers``."""
    if not usd_rub:
        return None
    return kop / 100.0 / usd_rub


def per_gpu_kop_h(offer: Json, interruptible: bool = False) -> Optional[float]:
    """Price per single GPU per hour. Offer prices are for the whole server."""
    price = offer["price"]["interruptible_kop_h" if interruptible else "on_demand_kop_h"]
    if price is None:
        return None
    return price / max(1, offer["gpu"]["count"])


def estimate_cost_minor(kop_h: Union[int, float], minutes: Union[int, float]) -> float:
    """Cost in minor units for ``minutes`` of runtime at ``kop_h`` per hour (billed per minute)."""
    return kop_h * minutes / 60.0


# -------------------------------------------------------------------------- client


class GpunzClient:
    """Thin wrapper around the gpu.nz API.

    Args:
        api_key: ``gpz_...`` key. Defaults to the ``GPUNZ_API_KEY`` environment variable.
            Not needed for the public catalog calls.
        base_url: API root. Defaults to ``GPUNZ_API_URL`` or ``https://gpu.nz/api/v1``.
        timeout: Per-request timeout in seconds.
        session: Optional preconfigured :class:`requests.Session`.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.api_key = api_key or os.environ.get(ENV_API_KEY) or None
        self.base_url = (base_url or os.environ.get(ENV_API_URL) or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"Accept": "application/json", "User-Agent": "gpunz-examples/1.0"})

    # ------------------------------------------------------------------ transport

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Json] = None,
        body: Optional[Json] = None,
        headers: Optional[Dict[str, str]] = None,
        auth: bool = False,
        retries: int = 2,
    ) -> Any:
        """Send one request and return the decoded JSON (``None`` for empty bodies).

        Safe methods (GET) are retried a couple of times on HTTP 429 and 5xx. Mutating
        requests are never retried automatically.
        """
        hdrs = dict(headers or {})
        if auth:
            if not self.api_key:
                raise AuthRequiredError(
                    f"{method} {path} needs an API key: set {ENV_API_KEY}=gpz_... "
                    "(create one in the console, or run `gpunz login`).",
                    code="unauthorized",
                )
            hdrs["Authorization"] = f"Bearer {self.api_key}"
        elif self.api_key:
            # Harmless on public endpoints; GET /templates then also returns your own templates.
            hdrs["Authorization"] = f"Bearer {self.api_key}"
        clean = {k: v for k, v in (params or {}).items() if v is not None}

        attempt = 0
        while True:
            try:
                resp = self.session.request(
                    method,
                    f"{self.base_url}{path}",
                    params=clean or None,
                    json=body,
                    headers=hdrs,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                if method == "GET" and attempt < retries:
                    attempt += 1
                    time.sleep(1.5 * attempt)
                    continue
                raise GpunzError(f"network error: {exc}") from exc
            if method == "GET" and attempt < retries and (resp.status_code == 429 or resp.status_code >= 500):
                attempt += 1
                try:
                    wait = float(resp.headers.get("Retry-After", 1.5 * attempt))
                except ValueError:
                    wait = 1.5 * attempt
                time.sleep(min(wait, 30.0))
                continue
            break
        return self._decode(resp)

    @staticmethod
    def _decode(resp: requests.Response) -> Any:
        if resp.status_code < 400:
            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()
        try:
            err = resp.json().get("error", {})
        except ValueError:
            err = {}
        raise GpunzError(
            err.get("message") or resp.text[:200] or f"HTTP {resp.status_code}",
            status=resp.status_code,
            code=err.get("code"),
            details=err.get("details"),
        )

    def _paginate(self, path: str, params: Json, max_items: Optional[int], auth: bool = False) -> Iterator[Json]:
        """Yield items page by page following ``next_cursor``."""
        params = dict(params)
        seen = 0
        while True:
            if max_items is not None:
                params["limit"] = max(1, min(200, max_items - seen))
            page = self._request("GET", path, params=params, auth=auth)
            for item in page["data"]:
                yield item
                seen += 1
                if max_items is not None and seen >= max_items:
                    return
            cursor = page.get("next_cursor")
            if not cursor:
                return
            params["cursor"] = cursor

    # -------------------------------------------------------------- public catalog

    def list_gpus(self) -> Json:
        """``GET /gpus``: GPU models with free count and the cheapest per-card price.

        Returns the full body: ``{"data": [...], "next_cursor": ..., "fx": {...}}`` so the
        dollar rate (``fx.usd_rub``) stays available. Use :meth:`iter_gpus` for plain rows.
        """
        return self._request("GET", "/gpus")

    def iter_gpus(self) -> Iterator[Json]:
        """Iterate over every GPU model, following ``next_cursor`` if the catalogue is paged."""
        return self._paginate("/gpus", {}, None)

    def search_offers_page(
        self,
        *,
        gpu: Optional[StrOrList] = None,
        num_gpus: Optional[Union[int, StrOrList]] = None,
        min_gpus: Optional[int] = None,
        type: Optional[str] = None,  # noqa: A002 - mirrors the API parameter name
        country: Optional[StrOrList] = None,
        min_reliability: Optional[float] = None,
        min_vram_gb: Optional[float] = None,
        max_price_kop_h: Optional[int] = None,
        verified: Optional[bool] = None,
        min_cuda: Optional[float] = None,
        min_disk_gb: Optional[float] = None,
        min_inet_down_mbps: Optional[float] = None,
        order: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Json:
        """``GET /offers``: one page of rentable offers (full body incl. ``fx``).

        Filters mirror the OpenAPI query parameters exactly. ``gpu`` takes exact model
        slugs from :meth:`list_gpus` (``"rtx-4090-24gb"``), not prefixes. ``order`` is one of
        ``price`` (default), ``-price``, ``dlperf``, ``dlperf_per_price``, ``reliability``,
        ``vram``, ``inet_down``. ``type`` is ``on_demand`` (default) or ``interruptible``.
        """
        params: Json = {
            "gpu": _csv(gpu),
            "num_gpus": _csv(num_gpus),
            "min_gpus": min_gpus,
            "type": type,
            "country": _csv(country),
            "min_reliability": min_reliability,
            "min_vram_gb": min_vram_gb,
            "max_price_kop_h": max_price_kop_h,
            "verified": None if verified is None else str(bool(verified)).lower(),
            "min_cuda": min_cuda,
            "min_disk_gb": min_disk_gb,
            "min_inet_down_mbps": min_inet_down_mbps,
            "order": order,
            "limit": limit,
            "cursor": cursor,
        }
        return self._request("GET", "/offers", params=params)

    def search_offers(self, *, limit: int = 50, **filters: Any) -> List[Json]:
        """Like :meth:`search_offers_page` but returns up to ``limit`` offers as a list.

        Follows ``next_cursor`` when ``limit`` exceeds one page (200 rows).
        """
        params: Json = {k: v for k, v in filters.items()}
        # Reuse the explicit signature for parameter normalisation.
        first = self.search_offers_page(limit=min(limit, 200), **params)
        offers: List[Json] = list(first["data"])
        cursor = first.get("next_cursor")
        while cursor and len(offers) < limit:
            page = self.search_offers_page(limit=min(200, limit - len(offers)), cursor=cursor, **params)
            offers.extend(page["data"])
            cursor = page.get("next_cursor")
        return offers[:limit]

    def get_offer(self, offer_id: str) -> Json:
        """``GET /offers/{id}``: full specification and prices of one offer."""
        return self._request("GET", f"/offers/{offer_id}")

    def list_templates(self) -> List[Json]:
        """``GET /templates``: the template catalogue (plus your own with a key)."""
        return list(self._paginate("/templates", {}, None))

    def get_template(self, slug: str) -> Json:
        """Find one template by slug (there is no single-template endpoint)."""
        for tpl in self.list_templates():
            if tpl["slug"] == slug:
                return tpl
        raise GpunzError(f"template {slug!r} not found", status=404, code="not_found")

    # ------------------------------------------------------------- account (key)

    def get_balance(self) -> Json:
        """``GET /balance`` (scope ``billing:read``)."""
        return self._request("GET", "/balance", auth=True)

    # ---------------------------------------------------------------- instances

    def create_instance(
        self,
        offer_id: str,
        template: str,
        disk_gb: int,
        *,
        name: Optional[str] = None,
        type: str = "on_demand",  # noqa: A002 - mirrors the API field name
        ssh_key_ids: Optional[List[str]] = None,
        image: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Json:
        """``POST /instances``: rent an offer. **This spends money** once the instance runs.

        The ``Idempotency-Key`` header makes retries safe: the same key returns the existing
        instance instead of renting a second one. A random key is generated when omitted;
        pass your own to make a whole script re-runnable.

        ``disk_gb`` must be 10-2000. ``image`` is only for the ``custom`` template.
        ``env`` and ``onstart`` are documented as "not supported yet" and are not exposed.
        """
        if not 10 <= disk_gb <= 2000:
            raise ValueError("disk_gb must be between 10 and 2000")
        body: Json = {"offer_id": offer_id, "template": template, "disk_gb": disk_gb, "type": type}
        if name:
            body["name"] = name[:60]
        if ssh_key_ids:
            body["ssh_key_ids"] = list(ssh_key_ids)
        if image:
            body["image"] = image
        key = (idempotency_key or uuid.uuid4().hex)[:64]
        return self._request("POST", "/instances", body=body, headers={"Idempotency-Key": key}, auth=True)

    def get_instance(self, instance_id: str) -> Json:
        """``GET /instances/{id}``."""
        return self._request("GET", f"/instances/{instance_id}", auth=True)

    def list_instances(self, include_destroyed: bool = False) -> List[Json]:
        """``GET /instances``: live instances (or all with ``include_destroyed=True``)."""
        params = {"status": "all"} if include_destroyed else {}
        return list(self._paginate("/instances", params, None, auth=True))

    def get_logs(self, instance_id: str, tail: int = 200) -> List[str]:
        """``GET /instances/{id}/logs``: last ``tail`` (1-1000) startup log lines."""
        out = self._request(
            "GET", f"/instances/{instance_id}/logs", params={"tail": max(1, min(1000, tail))}, auth=True
        )
        return list(out["lines"])

    def stop_instance(self, instance_id: str) -> Json:
        """``POST /instances/{id}/stop``: stop the GPU; only the disk keeps being billed."""
        return self._request("POST", f"/instances/{instance_id}/stop", auth=True)

    def start_instance(self, instance_id: str, accept_price: bool = False) -> Json:
        """``POST /instances/{id}/start``.

        If the market price changed the API answers ``409 price_changed`` (see
        ``GpunzError.details["new_kop_h"]``); call again with ``accept_price=True`` to proceed.
        """
        body: Optional[Json] = {"accept_price": True} if accept_price else None
        return self._request("POST", f"/instances/{instance_id}/start", body=body, auth=True)

    def destroy_instance(self, instance_id: str) -> Json:
        """``DELETE /instances/{id}``: irreversible, the disk and its data are removed."""
        return self._request("DELETE", f"/instances/{instance_id}", auth=True)

    # ------------------------------------------------------------------ helpers

    def wait_until_running(
        self,
        instance_id: str,
        *,
        timeout_s: float = 1200.0,
        poll_s: float = 10.0,
        require_ssh: bool = True,
        on_update: Optional[Callable[[Json], None]] = None,
    ) -> Json:
        """Poll :meth:`get_instance` until the instance is ``running`` (and SSH answers).

        Raises:
            InstanceStateError: the instance ended up failed/stopped/destroyed/outbid.
            TimeoutError: it did not become ready within ``timeout_s``. The instance keeps
                existing (and billing); inspect :meth:`get_logs` and stop or destroy it.
        """
        deadline = time.monotonic() + timeout_s
        while True:
            inst = self.get_instance(instance_id)
            if on_update:
                on_update(inst)
            status = inst.get("status")
            if status in _DEAD_STATES:
                raise InstanceStateError(
                    f"instance {instance_id} is {status} (stop_reason={inst.get('stop_reason')})", code=status
                )
            ssh = inst.get("ssh")
            if status == "running" and (not require_ssh or (ssh and ssh.get("ready"))):
                return inst
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"instance {instance_id} is still {status} after {timeout_s:.0f}s; "
                    "check the logs, then stop or destroy it if you do not need it."
                )
            time.sleep(poll_s)


def connection_info(instance: Json, include_password: bool = False) -> Json:
    """Extract how to reach an instance: SSH command/host/port and web URLs.

    The SSH root password is left out unless ``include_password=True``.
    """
    ssh = instance.get("ssh") or {}
    info: Json = {
        "id": instance.get("id"),
        "status": instance.get("status"),
        "ssh_command": ssh.get("command"),
        "ssh_host": ssh.get("host"),
        "ssh_port": ssh.get("port"),
        "ssh_user": ssh.get("user"),
        "ssh_ready": ssh.get("ready"),
        "urls": [{"label": u.get("label"), "url": u.get("url")} for u in instance.get("urls") or []],
    }
    if include_password:
        info["ssh_password"] = ssh.get("password")
    return info
