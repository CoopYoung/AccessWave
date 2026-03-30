from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.database import init_db
from app.errors import http_exception_handler as _http_exc_handler, unhandled_exception_handler as _unhandled_exc_handler, validation_exception_handler
from app.limiter import limiter
from app.logging_config import configure_logging
from app.routers import auth_router, backup_router, billing_router, health_router, scan_router, api_keys_router, webhooks_router
from app.scheduler import start_scheduler, stop_scheduler
from app.security_headers import SecurityHeadersMiddleware

configure_logging(log_level=settings.LOG_LEVEL, log_format=settings.LOG_FORMAT)
logger = structlog.get_logger("accesswave")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("startup_complete", log_level=settings.LOG_LEVEL, log_format=settings.LOG_FORMAT)
    start_scheduler()
    logger.info("AccessWave started")
    yield
    stop_scheduler()


_DESCRIPTION = """
**AccessWave** is a WCAG 2.1 accessibility scanner SaaS. Scan websites for
accessibility issues, track scores over time, and export results.

## Authentication

Most endpoints require a **Bearer JWT** obtained from `/api/auth/login` or
`/api/auth/register`. Pass it in the `Authorization` header:

```
Authorization: Bearer <token>
```

Alternatively you can pass a long-lived **API Key** (managed at `/api/keys`):

```
Authorization: Bearer aw_<key>
```

## Rate limits

| Scope | Default |
|-------|---------|
| General API | 60 req/min |
| Scan start | 10 req/min |
| Login | 10 req/min |
| Register | 5 req/min |

Exceeded limits return **429 Too Many Requests** with a `Retry-After` header.
"""

_TAGS: list[dict] = [
    {
        "name": "auth",
        "description": "Register, log in, manage your profile and password.",
    },
    {
        "name": "scans",
        "description": (
            "Create and manage **sites**, trigger **scans**, retrieve issues, "
            "compare results, and share public reports."
        ),
    },
    {
        "name": "api-keys",
        "description": "Create and revoke long-lived API keys for programmatic access.",
    },
    {
        "name": "webhooks",
        "description": "Register HTTPS endpoints to receive `scan.completed` / `scan.failed` events.",
    },
    {
        "name": "backup",
        "description": "Export all your data as JSON and restore it later.",
    },
    {
        "name": "health",
        "description": "Liveness and readiness probes for container orchestration.",
    },
]

app = FastAPI(
    title="AccessWave API",
    version="1.0.0",
    description=_DESCRIPTION,
    contact={"name": "AccessWave Support", "url": "https://accesswave.io"},
    license_info={"name": "MIT"},
    openapi_tags=_TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)
app.state.limiter = limiter

# Rate-limit handler must be registered before the generic HTTPException handler
# so that 429 responses still carry the Retry-After header added by slowapi.
# --- Middleware (registered in reverse order: last-added runs first) ----------

# 1. Rate limiting — must be outermost so limits apply before any other logic.
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Global handlers — registered after the rate-limit handler so slowapi wins on 429.
app.add_exception_handler(RequestValidationError, validation_exception_handler)

app.add_middleware(SlowAPIMiddleware)

# 2. CORS — handle preflight before reaching route handlers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# 3. Security headers — injected into every response on the way out.
app.add_middleware(SecurityHeadersMiddleware)

# -----------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(health_router.router)
app.include_router(auth_router.router)
app.include_router(scan_router.router)
app.include_router(billing_router.router)
app.include_router(api_keys_router.router)
app.include_router(webhooks_router.router)
app.include_router(backup_router.router)

# Instrument all HTTP endpoints and expose /metrics in Prometheus text format.
# The instrumentator collects: request count, request duration, response size,
# and in-flight requests — all labelled by method, handler, and status code.
Instrumentator(
    should_group_status_codes=False,
    excluded_handlers=["/metrics"],
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    if exc.status_code == 404:
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
    return templates.TemplateResponse("500.html", {"request": request}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=exc)
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
    return templates.TemplateResponse("500.html", {"request": request}, status_code=500)


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})
@app.get("/api-keys", response_class=HTMLResponse)
async def api_keys_page(request: Request):
    return templates.TemplateResponse("api_keys.html", {"request": request})


@app.get("/webhooks", response_class=HTMLResponse)
async def webhooks_page(request: Request):
    return templates.TemplateResponse("webhooks.html", {"request": request})
@app.get("/share/{token}", response_class=HTMLResponse)
async def shared_report_page(request: Request, token: str):
    return templates.TemplateResponse("shared_report.html", {"request": request, "token": token})


@app.get("/api-reference", response_class=HTMLResponse, include_in_schema=False)
async def api_reference_page(request: Request):
    return templates.TemplateResponse("api_reference.html", {"request": request})
