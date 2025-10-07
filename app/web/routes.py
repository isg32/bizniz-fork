from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.services import stripe_service, pocketbase_service

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
    The correct dependency for rendering templates.
    It gathers all necessary global context variables.
    """
    # 1. Get user from session
    current_user = None
    user_token = request.session.get("user_token")
    if user_token:
        current_user = pocketbase_service.get_user_from_token(user_token)
        if not current_user:
            request.session.clear() # Clear invalid session

    # 2. Return the complete context dictionary
    return {
        "request": request,
        "settings": settings,
        "current_user": current_user,
        "flash_messages": request.session.pop("flash_messages", [])
    }


def get_current_user_from_session(request: Request):
    """
    Dependency to protect routes by checking for a user in the session.
    If not found, it redirects to the login page.
    """
    if not request.session.get("user_token"):
        flash(request, "You need to be logged in to view that page.", "warning")
        return RedirectResponse(url="/login", status_code=303)
    return request.session.get("user_token")


# --- Web Page Routes ---

@router.get("/", response_class=HTMLResponse, tags=["Web Frontend"])
async def index(request: Request, context: dict = Depends(Tmpl)):
    """Serves the main landing page."""
    return templates.TemplateResponse("main/index.html", context)


@router.get("/dashboard", response_class=HTMLResponse, tags=["Web Frontend"])
async def dashboard(
    request: Request,
    context: dict = Depends(Tmpl),
    user_token: str = Depends(get_current_user_from_session)
):
    """Serves the user dashboard with transaction history."""
    payment_status = request.query_params.get("payment")
    if payment_status == "success":
        flash(request, "Your purchase was successful! Your account has been updated.", "success")
    
    user_id = request.session.get("user_id")
    transactions = pocketbase_service.get_user_transactions(user_id)
    context["transactions"] = transactions
    
    return templates.TemplateResponse("dashboard.html", context)


@router.get("/pricing", response_class=HTMLResponse, tags=["Web Frontend"])
async def pricing_page(
    request: Request,
    context: dict = Depends(Tmpl)
):
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
async def customer_portal(
    request: Request,
    user_token: str = Depends(get_current_user_from_session)
):
    """Redirects the user to the Stripe Customer Portal."""
    user_record = pocketbase_service.get_user_from_token(user_token)

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
    user_token: str = Depends(get_current_user_from_session) 
):
    """Creates a Stripe Checkout session and redirects the user to it."""
    user_id = request.session.get("user_id")
    if not user_id:
        flash(request, "You must be logged in to make a purchase.", "error")
        return RedirectResponse(url="/login", status_code=303)

    # Check if user already has an active subscription when trying to subscribe
    if mode == "subscription":
        user = pocketbase_service.get_user_by_id(user_id)
        if user and hasattr(user, 'subscription_status') and user.subscription_status == 'active':
            flash(request, "You already have an active subscription. Please manage it from your dashboard.", "warning")
            return RedirectResponse(url="/dashboard", status_code=303)

    session = stripe_service.create_checkout_session(price_id, user_id, request, mode)
    
    if session and session.url:
        return RedirectResponse(url=session.url, status_code=303)
    else:
        flash(request, "Could not create a payment session. Please try again.", "error")
        return RedirectResponse(url="/pricing", status_code=303)


@router.post("/cancel-subscription", tags=["Web Frontend"])
async def cancel_subscription(
    request: Request,
    user_token: str = Depends(get_current_user_from_session)
):
    """Cancels the user's active subscription."""
    user_id = request.session.get("user_id")
    if not user_id:
        flash(request, "You must be logged in to cancel a subscription.", "error")
        return RedirectResponse(url="/login", status_code=303)

    user = pocketbase_service.get_user_by_id(user_id)

    # Check if user has an active subscription
    if not user or user.subscription_status != 'active' or not user.stripe_subscription_id:
        flash(request, "You don't have an active subscription to cancel.", "error")
        return RedirectResponse(url="/dashboard", status_code=303)

    # Cancel the subscription via Stripe
    success = stripe_service.cancel_subscription(user.stripe_subscription_id)

    if success:
        flash(request, "Your subscription has been cancelled. You'll continue to have access until the end of your billing period.", "success")
    else:
        flash(request, "Failed to cancel subscription. Please try again or contact support.", "error")

    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/reactivate-subscription", tags=["Web Frontend"])
async def reactivate_subscription(
    request: Request,
    user_token: str = Depends(get_current_user_from_session)
):
    """Reactivates a subscription that was set to cancel."""
    user_id = request.session.get("user_id")
    if not user_id:
        flash(request, "You must be logged in to reactivate a subscription.", "error")
        return RedirectResponse(url="/login", status_code=303)

    user = pocketbase_service.get_user_by_id(user_id)

    # Check if user has a canceling subscription
    if not user or user.subscription_status != 'canceling':
        flash(request, "You don't have a subscription to reactivate.", "error")
        return RedirectResponse(url="/dashboard", status_code=303)

    # Check if the subscription still exists in Stripe (not expired yet)
    if not user.stripe_subscription_id:
        flash(request, "Your subscription has already ended and cannot be reactivated. Please subscribe again from the pricing page.", "warning")
        return RedirectResponse(url="/pricing", status_code=303)

    # Reactivate the subscription via Stripe
    success = stripe_service.reactivate_subscription(user.stripe_subscription_id)

    if success:
        flash(request, "Your subscription has been reactivated! It will continue to renew automatically.", "success")
    else:
        flash(request, "Failed to reactivate subscription. Please try again or contact support.", "error")

    return RedirectResponse(url="/dashboard", status_code=303)
