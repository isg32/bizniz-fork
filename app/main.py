# app/main.py

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from contextlib import asynccontextmanager
# - REMOVE: We will no longer use the ssl module for this workaround.
# import ssl 

# --- Application Imports ---
from app.core.config import settings
from app.api.v1 import api as api_v1
from app.web import routes as web_routes
from app.web import auth_routes as web_auth_routes

# --- Service Client Imports for Initialization ---
from app.services.internal import pocketbase_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages application startup and shutdown events.
    """
    # --- Code to run on startup ---
    print("Initializing services...")

    # --- ❌ REMOVED: The entire SSL unverified context block is gone. ---
    # This was a major security risk and has been removed.
    # Ensure your PocketBase server has a valid SSL/TLS certificate.
    
    # Initialize your internal services
    pocketbase_service.init_clients()
    print("PocketBase clients initialized.")
    yield  # --- The application runs here ---
    
    # --- Code to run on shutdown ---
    print("Application shutting down.")


# --- App Initialization ---
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# --- Middleware ---
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Static Files ---
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# --- Routers ---
app.include_router(api_v1.api_router, prefix=settings.API_V1_STR)
app.include_router(web_routes.router)
app.include_router(web_auth_routes.router)