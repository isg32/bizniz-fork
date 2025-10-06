
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.services import stripe_service

# Initialize the template engine
templates = Jinja2Templates(directory="app/templates")
router = APIRouter()

def flash(request: Request, message: str, category: str = "info"):
    """Helper function to add a flash message to the session."""
    if "flash_messages" not in request.session:
        request.session["flash_messages"] = []
    request.session["flash_messages"].append((category, message))

# --- Dependencies ---

def get_current_user_from_session(request: Request):
    """
    Dependency to check for a user in the session.
    If not found, it redirects to the login page.
    """
    if not request.session.get("user_token"):
        flash(request, "You need to be logged in to view that page.", "warning")
        return RedirectResponse(url="/login", status_code=303)
    return request.session.get("user_token")

async def Tmpl(request: Request):
    """
    Dependency that provides a dictionary of common context variables
    for rendering Jinja2 templates.
    """
    return { "request": request }

# --- Web Page Routes ---

@router.get("/", response_class=HTMLResponse, tags=["Web Frontend"])
async def index(context: dict = Depends(Tmpl)):
    """Serves the main landing page."""
    return templates.TemplateResponse("main/index.html", context)

@router.get("/dashboard", response_class=HTMLResponse, tags=["Web Frontend"])
async def dashboard(
    request: Request,
    context: dict = Depends(Tmpl),
    user_token: str = Depends(get_current_user_from_session)
):
    """
    Serves the user dashboard. The dependency ensures this route is protected.
    """
    # Flash message handling for successful payments
    payment_status = request.query_params.get("payment")
    if payment_status == "success":
        flash(request, "Your purchase was successful! Your account has been updated.", "success")

    return templates.TemplateResponse("dashboard.html", context)

@router.get("/pricing", response_class=HTMLResponse, tags=["Web Frontend"])
async def pricing_page(
    request: Request,
    context: dict = Depends(Tmpl)
):
    """
    Fetches products from Stripe and displays the pricing page.
    """
    # Flash message handling for cancelled payments
    payment_status = request.query_params.get("payment")
    if payment_status == "cancelled":
        flash(request, "Your purchase was cancelled.", "info")
    
    products = stripe_service.get_all_active_products_and_prices()
    context["products"] = products
    
    return templates.TemplateResponse("main/pricing.html", context)

@router.get("/policy", response_class=HTMLResponse, tags=["Web Frontend"])
async def policy_page(context: dict = Depends(Tmpl)):
    """Serves the privacy policy page."""
    return templates.TemplateResponse("main/policy.html", context)

# --- Form Handling Routes ---

@router.post("/create-checkout-session", tags=["Web Frontend"])
async def create_checkout_session(
    request: Request,
    price_id: str = Form(...),
    # This dependency protects the route AND gives us the user's token
    user_token: str = Depends(get_current_user_from_session) 
):
    """
    Creates a Stripe Checkout session and redirects the user to it.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        # This should not happen due to the dependency, but it's a good safeguard
        flash(request, "You must be logged in to make a purchase.", "error")
        return RedirectResponse(url="/login", status_code=303)

    session = stripe_service.create_checkout_session(price_id, user_id, request)
    
    if session and session.url:
        return RedirectResponse(url=session.url, status_code=303)
    else:
        flash(request, "Could not create a payment session. Please try again.", "error")
        return RedirectResponse(url="/pricing", status_code=303)
