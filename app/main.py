from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.api.v1 import api as api_v1
from app.web import routes as web_routes
from app.web import auth_routes as web_auth_routes
from app.services import pocketbase_service

# --- App Initialization ---
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# --- Middleware ---
# IMPORTANT: Middleware is processed in the order it's added.
# SessionMiddleware MUST come first to make `request.session` available
# to other middleware and the application.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY
)

# CORS should come after SessionMiddleware if you need to handle credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Startup Events ---
@app.on_event("startup")
def startup_event():
    """Initializes necessary services on application startup."""
    pocketbase_service.init_clients()
    print("PocketBase clients initialized.")


# --- Static Files ---
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# --- Routers ---
# The logic for global context variables is now handled by the `Tmpl`
# dependency within the route files, which is a cleaner pattern.
app.include_router(api_v1.api_router, prefix=settings.API_V1_STR)
app.include_router(web_routes.router)
app.include_router(web_auth_routes.router)

# NOTE: The root path ("/") is now handled by the `index` route in `app/web/routes.py`,
# which is included above. We no longer need a separate handler here.