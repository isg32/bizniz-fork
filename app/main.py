from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from contextlib import asynccontextmanager

# --- Application Imports ---
from app.core.config import settings
from app.api.v1 import api as api_v1
from app.web import routes as web_routes
from app.web import auth_routes as web_auth_routes

# --- Service Client Imports for Initialization ---
from app.services.internal import pocketbase_service
# Import the single, shared instance of our new Gemini client
from app.services.clients.gemini import gemini_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages application startup and shutdown events.
    This is the recommended modern way to handle initialization.
    """
    # --- Code to run on startup ---
    print("Initializing services...")

    # Initialize your internal services
    pocketbase_service.init_clients()
    print("PocketBase clients initialized.")
    
    # Initialize the unified Gemini client
    gemini_client.init_app()
    
    print("Service initialization complete. Application is ready.")
    
    yield  # --- The application runs here ---
    
    # --- Code to run on shutdown ---
    print("Application shutting down.")


# --- App Initialization ---
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan  # Wire up the lifespan manager
)

# --- Middleware ---
# IMPORTANT: Middleware is processed in the order it's added.
# SessionMiddleware MUST come first to make `request.session` available.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your domain
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