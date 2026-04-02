import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    health,
    uploads,
    auth,
    catalog,
    products,
    variants,
    templates,
    competitor_mapping,
    dictionaries,
    attributes,   # ✅ add
    stats,
    product_groups,
    yandex_market,
    ozon_market,
    marketplace_mapping,
    connectors_status,
    comfyui,
    catalog_exchange,
)
from app.core.auth import PUBLIC_API_PATHS, auth_from_request

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


# backend/
BACKEND_DIR = Path(__file__).resolve().parents[1]
# Global PIM/frontend/
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"
UPLOADS_DIR = BACKEND_DIR / "data" / "uploads"

if load_dotenv:
    load_dotenv(BACKEND_DIR / ".env")

DEV_PROXY = os.getenv("DEV_PROXY", "1") == "1"
VITE_ORIGIN = os.getenv("VITE_ORIGIN", "http://127.0.0.1:5173")
VITE_ORIGINS = [
    o.strip()
    for o in os.getenv("VITE_ORIGINS", "").split(",")
    if o.strip()
] or [VITE_ORIGIN, "http://localhost:5173"]

app = FastAPI(title="Global Trade PIM API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)

# =========================
# API
# =========================
app.include_router(health.router, prefix="/api")
app.include_router(uploads.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(variants.router, prefix="/api")
app.include_router(templates.router, prefix="/api")
app.include_router(competitor_mapping.router, prefix="/api")
app.include_router(dictionaries.router, prefix="/api")
app.include_router(attributes.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(product_groups.router, prefix="/api")
app.include_router(yandex_market.router, prefix="/api")
app.include_router(ozon_market.router, prefix="/api")
app.include_router(marketplace_mapping.router, prefix="/api")
app.include_router(connectors_status.router, prefix="/api")
app.include_router(comfyui.router, prefix="/api")
app.include_router(catalog_exchange.router, prefix="/api")


@app.middleware("http")
async def _auth_guard_middleware(request: Request, call_next):
    path = request.url.path
    if path == "/api" or path.startswith("/api/"):
        if not path.startswith("/api/uploads") and path not in PUBLIC_API_PATHS:
            auth_ctx = auth_from_request(request)
            request.state.auth = auth_ctx
            if not auth_ctx.user:
                return Response('{"detail":"AUTH_REQUIRED"}', status_code=401, media_type="application/json")
        else:
            request.state.auth = auth_from_request(request)
    return await call_next(request)


@app.on_event("startup")
async def _startup_connectors_scheduler() -> None:
    connectors_status.start_scheduler()


@app.on_event("shutdown")
async def _shutdown_connectors_scheduler() -> None:
    await connectors_status.stop_scheduler()

# =========================
# PROD: static assets
# =========================
if DIST_DIR.exists():
    assets_dir = DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# =========================
# DEV: proxy to Vite
# =========================
async def _proxy_to_vite(request: Request, path: str) -> Response:
    # headers: убираем то, что мешает прокси
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)

    body = await request.body()

    last_error: Exception | None = None
    r: httpx.Response | None = None
    for origin in VITE_ORIGINS:
        url = f"{origin}/{path}" if path else f"{origin}/"
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                r = await client.request(
                    method=request.method,
                    url=url,
                    params=request.query_params,
                    content=body,
                    headers=headers,
                )
            break
        except httpx.RequestError as e:
            last_error = e
    else:
        return Response(
            content=f"Vite dev server is not reachable: {last_error}",
            status_code=502,
        )

    if r is None:
        return Response(
            content=f"Vite dev server is not reachable: {last_error}",
            status_code=502,
        )

    resp_headers = dict(r.headers)
    # эти заголовки либо конфликтуют, либо выставятся автоматически
    for h in ["content-encoding", "transfer-encoding", "connection", "content-length"]:
        resp_headers.pop(h, None)

    status = r.status_code
    if status < 200:
        status = 200
    return Response(content=r.content, status_code=status, headers=resp_headers)


# =========================
# SPA fallback / router
# =========================
@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def spa_or_proxy(request: Request, path: str):
    # 1) не трогаем API
    if path == "api" or path.startswith("api/"):
        return Response(status_code=404)

    # 1.1) не проксируем websocket upgrade (h11 не принимает 101)
    if (request.headers.get("upgrade") or "").lower() == "websocket":
        return Response(status_code=204)

    # 2) не трогаем assets (и в DEV, и в PROD)
    if path == "assets" or path.startswith("assets/"):
        # в DEV assets отдаёт Vite (если надо), а в PROD — mount выше
        if DEV_PROXY:
            return await _proxy_to_vite(request, path)
        return Response(status_code=404)

    # 3) DEV: прокси на Vite для всего остального
    if DEV_PROXY:
        return await _proxy_to_vite(request, path)

    # 4) PROD: SPA index.html (fallback на любой роут)
    index_file = DIST_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    return Response(
        "Frontend not built. Run `npm run build` in /frontend.",
        status_code=500,
    )
