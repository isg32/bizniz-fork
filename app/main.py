# app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# --- Application Imports ---
from app.core.config import settings

# 🔴 OLD LINE: from app.api.v1 import api as api_v1
# ✅ NEW LINE: Import the actual router object directly.
from app.api.v1 import api_router

# --- Service Client Imports for Initialization ---
from app.services.internal import pocketbase_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages application startup and shutdown events.
    """
    # --- Code to run on startup ---
    print("Initializing services for API...")

    # Initialize your internal services
    pocketbase_service.init_clients()
    print("PocketBase clients initialized.")
    yield  # --- The application runs here ---

    # --- Code to run on shutdown ---
    print("API shutting down.")


# --- App Initialization ---
app = FastAPI(
    title=f"{settings.PROJECT_NAME} API",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    description="The headless API for all application services.",
    version="1.0.0",
    lifespan=lifespan,
)

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://www.bugswriter.ai",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Routers ---

# The API router is now the only router for the entire application.
# 🔴 OLD LINE: app.include_router(api_v1.api_router, prefix=settings.API_V1_STR)
# ✅ NEW LINE: Use the directly imported router object.
app.include_router(api_router, prefix=settings.API_V1_STR)


# A simple root endpoint for health checks
@app.get("/", tags=["Health Check"])
def read_root():
    """A simple health check endpoint."""
    return {"status": "ok", "project": settings.PROJECT_NAME}
