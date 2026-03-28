import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import init_db
from app.errors import http_exception_handler, unhandled_exception_handler, validation_exception_handler
from app.limiter import limiter
from app.routers import auth_router, billing_router, scan_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("accesswave")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("AccessWave started")
    yield


app = FastAPI(title="AccessWave", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter

# Rate-limit handler must be registered before the generic HTTPException handler
# so that 429 responses still carry the Retry-After header added by slowapi.
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Global handlers — registered after the rate-limit handler so slowapi wins on 429.
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.add_middleware(SlowAPIMiddleware)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(auth_router.router)
app.include_router(scan_router.router)
app.include_router(billing_router.router)


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
