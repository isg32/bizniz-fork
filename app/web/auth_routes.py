
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.services import pocketbase_service

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(tags=["Web Auth"])

def flash(request: Request, message: str, category: str = "info"):
    """Helper function to add a flash message to the session."""
    if "flash_messages" not in request.session:
        request.session["flash_messages"] = []
    request.session["flash_messages"].append((category, message))

# --- Registration Routes ---

@router.get("/register", response_class=HTMLResponse)
async def get_registration_page(request: Request):
    """Serves the user registration page."""
    return templates.TemplateResponse(
        "auth/register.html",
        {"request": request}
    )

@router.post("/register", response_class=HTMLResponse)
async def handle_registration(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...)
):
    """Handles the form submission for user registration."""
    if password != password_confirm:
        flash(request, "Passwords do not match.", "error")
        return RedirectResponse(url="/register", status_code=303)

    record, error = pocketbase_service.create_user(email, password, name)

    if error:
        # Check for specific, common errors
        if "validation_not_unique" in str(error):
            flash(request, "This email address is already registered. Please try logging in.", "warning")
        else:
            flash(request, f"An unknown registration error occurred.", "error")
        return RedirectResponse(url="/register", status_code=303)

    # Success! Show the message page.
    return templates.TemplateResponse(
        "auth/message.html",
        {
            "request": request,
            "title": "Verification Required",
            "message": "We've sent a verification link to your email. Please click it to activate your account."
        }
    )

# --- Email Verification Route ---

@router.get("/verify-email/{token}", response_class=HTMLResponse)
async def verify_email(request: Request, token: str):
    """Handles the email verification link clicked by the user."""
    success, error = pocketbase_service.confirm_verification(token)
    
    if success:
        flash(request, "Your email has been verified successfully! You can now log in.", "success")
        return RedirectResponse(url="/login", status_code=303)
    else:
        flash(request, f"Email verification failed. The link may be expired or invalid.", "error")
        return RedirectResponse(url="/register", status_code=303)

@router.get("/login", response_class=HTMLResponse)
async def get_login_page(request: Request):
    """Serves the user login page."""
    # If user is already logged in, redirect them to the dashboard
    if request.session.get("user_token"):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("auth/login.html", {"request": request})

@router.post("/login", response_class=HTMLResponse)
async def handle_login(request: Request, email: str = Form(...), password: str = Form(...)):
    """Handles the form submission for user login."""
    auth_data = pocketbase_service.auth_with_password(email, password)

    if not auth_data:
        flash(request, "Invalid email or password.", "error")
        return RedirectResponse(url="/login", status_code=303)

    if not auth_data.record.verified:
        flash(request, "Your account is not verified. Please check your email for the verification link.", "warning")
        return RedirectResponse(url="/login", status_code=303)

    # Login successful, store token in session
    request.session["user_token"] = auth_data.token
    request.session["user_id"] = auth_data.record.id
    
    flash(request, "Logged in successfully!", "success")
    return RedirectResponse(url="/dashboard", status_code=303)

@router.get("/logout")
async def logout(request: Request):
    """Clears the user session and logs them out."""
    request.session.clear()
    flash(request, "You have been logged out.", "info")
    return RedirectResponse(url="/", status_code=303)
