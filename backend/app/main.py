"""JobPilot API — FastAPI backend for Render deployment.

Pure JSON API. No templates, no static files. The frontend is a
separate Next.js app on Vercel at shreevaidya.com.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.logger import log
from app.routes import health, profile, jobs, scraper, applications, answers


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("JobPilot API starting up")
    yield
    log.info("JobPilot API shutting down")


app = FastAPI(
    title="JobPilot API",
    version="4.0.0",
    lifespan=lifespan,
)

# ── CORS — allow frontend + Chrome extension ─────────────────────────────────

settings = get_settings()
origins = [
    settings.frontend_url,              # https://shreevaidya.com
    "http://localhost:3000",             # local frontend dev
    "http://127.0.0.1:3000",
    "chrome-extension://*",             # Chrome extension
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers ─────────────────────────────────────────────────────────

app.include_router(health.router)
app.include_router(profile.router)
app.include_router(jobs.router)
app.include_router(scraper.router)
app.include_router(applications.router)
app.include_router(answers.router)


@app.get("/")
async def root():
    return {
        "service": "jobpilot-api",
        "version": "4.0.0",
        "docs": "/docs",
    }
