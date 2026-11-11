import os
from mimetypes import guess_type
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy import inspect, text

from apps.api.config import settings
from apps.api.database import engine, Base
from apps.api.seed import seed_data
from apps.api.preview_catalog import complete_preview_catalog
from apps.api.models import StoreSettings
from apps.api.database import AsyncSessionLocal
from sqlalchemy import select
from decimal import Decimal
from apps.api.routers import (
    auth, products, banners, pricing, orders, cart,
    admin_dashboard, admin_settings, admin_orders, admin_products, admin_export,
    promocodes, custom_requests, admin_messages
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure uploads directories exist
    os.makedirs(os.path.join(settings.UPLOAD_DIR, "receipts"), exist_ok=True)
    (Path(settings.UPLOAD_DIR) / "products").mkdir(parents=True, exist_ok=True)
    
    # Auto-migrate / seed if needed
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        columns = await conn.run_sync(lambda sync: {column["name"] for column in inspect(sync).get_columns("orders")})
        for name, sql_type in (
            ("promo_code", "VARCHAR(50)"),
            ("promo_discount_rub", "NUMERIC(10, 2) DEFAULT 0.00"),
            ("tracking_url", "VARCHAR(500)"),
        ):
            if name not in columns:
                await conn.execute(text(f"ALTER TABLE orders ADD COLUMN {name} {sql_type}"))
    
    if settings.DEV_AUTH_ENABLED:
        await seed_data()
        if os.getenv("GRMV_REFERENCE_PREVIEW") == "1":
            await complete_preview_catalog()
    else:
        async with AsyncSessionLocal() as session:
            if await session.scalar(select(StoreSettings.id).limit(1)) is None:
                session.add(StoreSettings(exchange_rate=Decimal("0"), payment_is_configured=False,
                                          shipping_provider_name="GRMV xLUCH store", shipping_calc_url=""))
                await session.commit()

    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static file mounts
app.mount("/uploads/products", StaticFiles(directory=Path(settings.UPLOAD_DIR) / "products", check_dir=False), name="product_uploads")

if os.path.exists("apps/web/public"):
    app.mount("/products", StaticFiles(directory="apps/web/public/products"), name="products_static")
    app.mount("/banners", StaticFiles(directory="apps/web/public/banners"), name="banners_static")
    app.mount("/images", StaticFiles(directory="apps/web/public/images"), name="images_static")

# Include Routers
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(products.router, prefix=settings.API_V1_STR)
app.include_router(banners.router, prefix=settings.API_V1_STR)
app.include_router(pricing.router, prefix=settings.API_V1_STR)
app.include_router(orders.router, prefix=settings.API_V1_STR)
app.include_router(cart.router, prefix=settings.API_V1_STR)
app.include_router(admin_dashboard.router, prefix=settings.API_V1_STR)
app.include_router(admin_settings.router, prefix=settings.API_V1_STR)
app.include_router(admin_orders.router, prefix=settings.API_V1_STR)
app.include_router(admin_products.router, prefix=settings.API_V1_STR)
app.include_router(admin_export.router, prefix=settings.API_V1_STR)
app.include_router(promocodes.router, prefix=settings.API_V1_STR)
app.include_router(custom_requests.router, prefix=settings.API_V1_STR)
app.include_router(admin_messages.router, prefix=settings.API_V1_STR)

@app.get(f"{settings.API_V1_STR}/health")
async def healthcheck():
    return {
        "status": "ok",
        "service": "GRMV xLUCH store API",
        "version": settings.VERSION,
        "dev_mode": settings.DEV_AUTH_ENABLED
    }

@app.middleware("http")
async def prevent_private_caching(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    elif request.url.path.startswith("/assets/") and response.status_code == 200:
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


if os.getenv("GRMV_SERVE_FRONTEND") == "1":
    app.add_middleware(GZipMiddleware, minimum_size=2048, compresslevel=5)
    dist = Path(__file__).resolve().parents[2] / "apps" / "web" / "dist"
    if not (dist / "index.html").is_file():
        raise RuntimeError("Build the Mini App before starting the public API.")

    app.mount("/reference", StaticFiles(directory=dist / "reference"), name="frontend_reference")

    @app.get("/assets/{filename}")
    async def frontend_asset(filename: str, request: Request):
        path = dist / "assets" / filename
        if path.suffix not in {".js", ".css"} or not path.is_file():
            raise HTTPException(404)
        media_type = guess_type(filename)[0]
        accepted = {}
        for value in request.headers.get("accept-encoding", "").split(","):
            encoding, _, priority = value.strip().lower().partition(";")
            try:
                accepted[encoding] = float(priority.strip().removeprefix("q=")) if priority else 1.0
            except ValueError:
                continue
        headers = {"Vary": "Accept-Encoding"}
        for encoding, suffix in (("br", ".br"), ("gzip", ".gz")):
            compressed = path.with_name(filename + suffix)
            if accepted.get(encoding, accepted.get("*", 0)) > 0 and compressed.is_file():
                return FileResponse(compressed, media_type=media_type,
                                    headers={**headers, "Content-Encoding": encoding})
        return FileResponse(path, media_type=media_type, headers=headers)

    @app.get("/catalog/{filename}")
    async def catalog_image(filename: str):
        if not filename.endswith(".webp") or not filename.removesuffix(".webp").isdigit():
            raise HTTPException(404)
        path = dist / "catalog" / filename
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/")
    @app.get("/{route:path}")
    async def mini_app(route: str = ""):
        pages = {"", "catalog", "favorites", "product", "calculator", "cart", "checkout", "orders", "profile", "admin"}
        if route.split("/")[0] not in pages:
            raise HTTPException(404)
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})
else:
    @app.get("/")
    async def root():
        return {"message": "GRMV xLUCH store API is running", "health": f"{settings.API_V1_STR}/health"}
