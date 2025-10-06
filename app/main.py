from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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
# Set up CORS (Cross-Origin Resource Sharing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY
)

# --- PocketBase Initialization ---
# This is a crucial step. We initialize the PocketBase clients when the app starts.
@app.on_event("startup")
def startup_event():
    """Initializes PocketBase clients on application startup."""
    pocketbase_service.init_clients()
    print("PocketBase clients initialized.")
    # You could add initializations for other services like Stripe here too
    # stripe_service.init(settings.STRIPE_API_KEY)


# --- Static Files and Templates Mounting ---
# This allows FastAPI to serve CSS, JS, and image files.
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# This sets up the Jinja2 templating engine for our web pages.
templates = Jinja2Templates(directory="app/templates")

# --- Global Template Variables ---
# This makes certain variables available in all Jinja2 templates.
@app.middleware("http")
async def add_global_template_vars(request: Request, call_next):
    """
    Injects global variables into the Jinja2 templates context.
    Also handles retrieving flash messages and the current user from the session.
    """
    flash_messages = request.session.pop("flash_messages", [])
    
    # --- NEW: Fetch current user from session token ---
    current_user = None
    user_token = request.session.get("user_token")
    if user_token:
        # This function fetches the latest user data from PocketBase
        current_user = pocketbase_service.get_user_from_token(user_token)
        if not current_user:
            # Token is invalid or expired, clear the session
            request.session.clear()

    response = await call_next(request)
    
    if "text/html" in response.headers.get("content-type", ""):
        # This is a bit of a workaround to inject context into TemplateResponse
        # after it's been created.
        response.context["settings"] = settings
        response.context["flash_messages"] = flash_messages
        response.context["current_user"] = current_user # <-- Add user to context
    
    return response

# --- Routers ---
# Include the API router
app.include_router(api_v1.api_router, prefix=settings.API_V1_STR)

# Include the Web routers
app.include_router(web_routes.router)
app.include_router(web_auth_routes.router)


# --- Root Endpoint ---
@app.get("/", include_in_schema=False)
async def read_root(request: Request):
    """
    Redirects the root URL to the main index page.
    This is for convenience. The actual index page is handled by web/routes.py.
    """
    return await web_routes.index(request)
