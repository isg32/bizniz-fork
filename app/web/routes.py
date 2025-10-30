from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.services.internal import stripe_service, pocketbase_service

# Initialize the template engine
templates = Jinja2Templates(directory="app/templates")
router = APIRouter()

def flash(request: Request, message: str, category: str = "info"):
    """Helper function to add a flash message to the session."""
    if "flash_messages" not in request.session:
        request.session["flash_messages"] = []
    request.session["flash_messages"].append((category, message))


# --- Dependencies ---

async def Tmpl(request: Request):
    """
    Enhanced template dependency with session validation.
    """
    current_user = None
    user_token = request.session.get("user_token")
    user_id_in_session = request.session.get("user_id")

    if user_token and user_id_in_session:
        # Get user from token
        current_user = pocketbase_service.get_user_from_token(user_token)

        # ✅ CRITICAL FIX: Validate that the token's user matches the session's user_id
        if current_user:
            if current_user.id != user_id_in_session:
                request.session.clear()
                current_user = None
        else:
            # Token is invalid or expired
            request.session.clear()

    return {
        "request": request,
        "settings": settings,
        "current_user": current_user,
        "flash_messages": request.session.pop("flash_messages", [])
    }

# --- Web Page Routes ---

@router.get("/", response_class=HTMLResponse, tags=["Web Frontend"])
async def index(request: Request, context: dict = Depends(Tmpl)):
    """Serves the main landing page."""
    return templates.TemplateResponse("main/index.html", context)


@router.get("/dashboard", response_class=HTMLResponse, tags=["Web Frontend"])
async def dashboard(request: Request, context: dict = Depends(Tmpl)):
    """Serves the user dashboard with transaction history."""

    # --- ✅ ADDED: Correct auth check ---
    current_user = context.get("current_user")
    if not current_user:
        flash(request, "You must be logged in to view the dashboard.", "warning")
        return RedirectResponse(url="/login", status_code=303)
    # --- End of fix ---

    payment_status = request.query_params.get("payment")
    if payment_status == "success":
        flash(request, "Your purchase was successful! Your account has been updated.", "success")

    # --- ✅ UPDATED: Use the validated user object ---
    user_id = current_user.id
    transactions = pocketbase_service.get_user_transactions(user_id)
    context["transactions"] = transactions

    return templates.TemplateResponse("dashboard.html", context)


@router.get("/pricing", response_class=HTMLResponse, tags=["Web Frontend"])
async def pricing_page(request: Request, context: dict = Depends(Tmpl)):
    """Fetches products from Stripe and displays the pricing page."""
    payment_status = request.query_params.get("payment")
    if payment_status == "cancelled":
        flash(request, "Your purchase was cancelled.", "info")

    subscription_plans, one_time_packs = stripe_service.get_all_active_products_and_prices()
    context["subscription_plans"] = subscription_plans
    context["one_time_packs"] = one_time_packs

    return templates.TemplateResponse("main/pricing.html", context)


@router.get("/policy", response_class=HTMLResponse, tags=["Web Frontend"])
async def policy_page(request: Request, context: dict = Depends(Tmpl)):
    """Serves the privacy policy page."""
    return templates.TemplateResponse("main/policy.html", context)


@router.get("/customer-portal", tags=["Web Frontend"])
async def customer_portal(request: Request, context: dict = Depends(Tmpl)):
    """Redirects the user to the Stripe Customer Portal."""

    user_record = context.get("current_user")
    if not user_record:
        flash(request, "You must be logged in to manage your billing.", "warning")
        return RedirectResponse(url="/login", status_code=303)

    if not user_record or not user_record.stripe_customer_id:
        flash(request, "No billing information found to manage.", "error")
        return RedirectResponse(url="/dashboard", status_code=303)

    portal_session = stripe_service.create_customer_portal_session(user_record.stripe_customer_id, request)

    if portal_session and portal_session.url:
        return RedirectResponse(url=portal_session.url, status_code=303)
    else:
        flash(request, "Could not open the customer portal. Please contact support.", "error")
        return RedirectResponse(url="/dashboard", status_code=303)


# --- Form Handling Routes ---

@router.post("/create-checkout-session", tags=["Web Frontend"])
async def create_checkout_session(
    request: Request,
    price_id: str = Form(...),
    mode: str = Form(...),
    context: dict = Depends(Tmpl)
):
    """Creates a Stripe Checkout session and redirects the user to it."""

    user = context.get("current_user")
    if not user:
        flash(request, "You must be logged in to make a purchase.", "error")
        return RedirectResponse(url="/login", status_code=303)
    user_id = user.id

    if mode == "subscription":
        if user and hasattr(user, 'subscription_status') and user.subscription_status == 'active':
            flash(request, "You already have an active subscription. Please manage it from your dashboard.", "warning")
            return RedirectResponse(url="/dashboard", status_code=303)

    session = stripe_service.create_checkout_session(price_id, user_id, request, mode)

    if session and session.url:
        return RedirectResponse(url=session.url, status_code=303)
    else:
        flash(request, "Could not create a payment session. Please try again.", "error")
        return RedirectResponse(url="/pricing", status_code=303)


