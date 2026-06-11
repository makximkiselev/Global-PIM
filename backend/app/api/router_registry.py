from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from fastapi import FastAPI

from app.api.routes import (
    attributes,
    auth,
    catalog,
    catalog_exchange,
    comfyui,
    competitor_mapping,
    connectors_status,
    dictionaries,
    health,
    info_models,
    marketplace_mapping,
    ozon_market,
    platform,
    product_groups,
    products,
    stats,
    templates,
    uploads,
    variants,
    yandex_market,
)


@dataclass(frozen=True)
class ApiRouterEntry:
    zone: str
    module: object
    purpose: str


API_ROUTER_ENTRIES: tuple[ApiRouterEntry, ...] = (
    ApiRouterEntry("system", health, "health checks"),
    ApiRouterEntry("system", uploads, "file upload delivery"),
    ApiRouterEntry("admin", auth, "authentication and access bootstrap"),
    ApiRouterEntry("admin", platform, "organizations and tenant context"),
    ApiRouterEntry("overview", stats, "dashboard stats and readiness"),
    ApiRouterEntry("products", catalog, "catalog categories and catalog product views"),
    ApiRouterEntry("products", products, "product cards and SKU operations"),
    ApiRouterEntry("products", variants, "legacy variant operations"),
    ApiRouterEntry("products", product_groups, "product groups and SKU grouping"),
    ApiRouterEntry("data_prep", templates, "info-model templates"),
    ApiRouterEntry("data_prep", info_models, "info-model assembly helpers"),
    ApiRouterEntry("data_prep", dictionaries, "dictionaries and normalized values"),
    ApiRouterEntry("data_prep", attributes, "attribute proposals and mapping"),
    ApiRouterEntry("data_prep", competitor_mapping, "competitor discovery and enrichment evidence"),
    ApiRouterEntry("data_prep", comfyui, "media generation jobs"),
    ApiRouterEntry("channels", yandex_market, "Yandex Market channel API"),
    ApiRouterEntry("channels", ozon_market, "Ozon channel API"),
    ApiRouterEntry("channels", marketplace_mapping, "marketplace category/parameter/value mapping"),
    ApiRouterEntry("channels", connectors_status, "connector accounts, probes, and scheduler"),
    ApiRouterEntry("channels", catalog_exchange, "catalog import/export runs"),
)


def iter_api_router_entries(zone: str | None = None) -> Iterable[ApiRouterEntry]:
    for entry in API_ROUTER_ENTRIES:
        if zone is None or entry.zone == zone:
            yield entry


def include_api_routers(app: FastAPI, prefix: str = "/api") -> None:
    for entry in API_ROUTER_ENTRIES:
        app.include_router(entry.module.router, prefix=prefix)  # type: ignore[attr-defined]
