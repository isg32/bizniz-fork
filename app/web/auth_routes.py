from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

# We need to import the Tmpl dependency from the other route file
from app.web.routes import Tmpl, flash
from app.services import pocketbase_service

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(tags=["Web Auth"])


# --- Registration Routes ---

@router.get("/register", response_class=HTMLResponse)
async def get_registration_page(request: Request, context: dict = Depends(Tmpl)):
    """Serves the user registration page."""
    return templates.TemplateResponse("auth/register.html", context)


@router.post("/register", response_class=HTMLResponse)
async def handle_registration(
    request: Request,
    context: dict = Depends(Tmpl), # Add context for re-rendering on error
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...)
):
    """Handles the form submission for user registration."""
    if password != password_confirm:
        flash(request, "Passwords do not match.", "error")
        # Re-render the page with the error message
        # You need a new Tmpl call here to get fresh flash messages
        new_context = await Tmpl(request)
        return templates.TemplateResponse("auth/register.html", new_context)

    record, error = pocketbase_service.create_user(email, password, name)

    if error:
        if "validation_not_unique" in str(error):
            flash(request, "This email address is already registered. Please try logging in.", "warning")
        else:
            flash(request, f"An unknown registration error occurred.", "error")
        # Re-render with the error
        new_context = await Tmpl(request)
        return templates.TemplateResponse("auth/register.html", new_context)
    
    context["title"] = "Verification Required"
    context["message"] = "We've sent a verification link to your email. Please click it to activate your account."
    return templates.TemplateResponse("auth/message.html", context)


@router.get("/verify-email/{token}", response_class=HTMLResponse)
async def verify_email(request: Request, token: str):
    """Handles the email verification link clicked by the user."""
    # This route doesn't render a template, it only redirects, so it doesn't need Tmpl.
    success, error = pocketbase_service.confirm_verification(token)
    
    if success:
        flash(request, "Your email has been verified successfully! You can now log in.", "success")
        return RedirectResponse(url="/login", status_code=303)
    else:
        flash(request, f"Email verification failed. The link may be expired or invalid.", "error")
        return RedirectResponse(url="/register", status_code=303)


# --- Login and Logout Routes ---

@router.get("/login", response_class=HTMLResponse)
async def get_login_page(request: Request, context: dict = Depends(Tmpl)):
    """Serves the user login page."""
    if request.session.get("user_token"):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("auth/login.html", context)


@router.post("/login", response_class=HTMLResponse)
async def handle_login(request: Request, email: str = Form(...), password: str = Form(...)):
    """Handles the form submission for user login."""
    auth_data = pocketbase_service.auth_with_password(email, password)

    if not auth_data:
        flash(request, "Invalid email or password.", "error")
        return RedirectResponse(url="/login?error=invalid", status_code=303)

    if not auth_data.record.verified:
        flash(request, "Your account is not verified. Please check your email for the verification link.", "warning")
        return RedirectResponse(url="/login?error=unverified", status_code=303)

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


# --- Password Reset Routes ---

@router.get("/forgot-password", response_class=HTMLResponse)
async def get_forgot_password_page(request: Request, context: dict = Depends(Tmpl)):
    """Serves the forgot password page."""
    return templates.TemplateResponse("auth/forgot_password.html", context)


@router.post("/forgot-password", response_class=HTMLResponse)
async def handle_forgot_password(request: Request, context: dict = Depends(Tmpl), email: str = Form(...)):
    """Handles the request to send a password reset email via PocketBase."""
    pocketbase_service.request_password_reset(email)
    
    context["title"] = "Check Your Email"
    context["message"] = "If an account with that email exists, we've sent a link to reset your password."
    return templates.TemplateResponse("auth/message.html", context)


@router.get("/reset-password/{token}", response_class=HTMLResponse)
async def get_reset_password_page(request: Request, token: str, context: dict = Depends(Tmpl)):
    """Serves the page where the user can enter their new password."""
    context["token"] = token
    return templates.TemplateResponse("auth/reset_password_form.html", context)


@router.post("/reset-password/{token}", response_class=HTMLResponse)
async def handle_reset_password(
    request: Request,
    token: str,
    password: str = Form(...),
    password_confirm: str = Form(...)
):
    """Handles the form submission for resetting the password."""
    if password != password_confirm:
        flash(request, "Passwords do not match.", "error")
        return RedirectResponse(url=f"/reset-password/{token}", status_code=303)

    success, error = pocketbase_service.confirm_password_reset(token, password, password_confirm)
    
    if success:
        flash(request, "Your password has been reset successfully. Please log in.", "success")
        return RedirectResponse(url="/login", status_code=303)
    else:
        flash(request, "Failed to reset password. The link may be invalid or expired.", "error")
        return RedirectResponse(url=f"/reset-password/{token}", status_code=303)