import logging
import os

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.chat_routes import router as chat_router
from app.api.market_routes import router as market_router
from app.api.routes import router
from app.config import get_settings
from app.errors import AppError, app_error_handler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = get_settings()

app = FastAPI(
    title="McXus Core API",
    version="0.1.0",
    description="Identity, Stars wallet, double-entry ledger and escrow. "
    + ("**SANDBOX: test Stars only, no real money.**" if settings.sandbox_mode else ""),
)
app.add_exception_handler(AppError, app_error_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith(settings.media_url + "/"):
        response.headers["Cache-Control"] = "public, max-age=604800, immutable"  # photos never change; save data
    else:
        response.headers["Cache-Control"] = "no-store"
    return response


# Raised whenever the app needs new server features, so an old server is reported clearly instead of "Not Found".
# 1 = M1-M2, 2 = M3 chat, 3 = M3.1 places, 4 = M3.2 groups/media/push.
API_LEVEL = 4


@app.get("/health", tags=["health"])
def health() -> dict[str, object]:
    return {"status": "ok", "sandbox": settings.sandbox_mode, "api_level": API_LEVEL}


app.include_router(router)
app.include_router(market_router)
app.include_router(chat_router)

# Listing photos (public). Replaced by object storage + CDN before launch.
os.makedirs(settings.media_dir, exist_ok=True)
app.mount(settings.media_url, StaticFiles(directory=settings.media_dir), name="media")
