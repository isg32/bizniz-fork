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


# --- OAuth Routes ---

@router.get("/auth/oauth2/{provider}")
async def oauth2_login(request: Request, provider: str):
    """Initiates OAuth2 login flow by redirecting to the provider."""
    # Get OAuth2 provider info from PocketBase
    providers = pocketbase_service.get_oauth2_providers()
    provider_data = next((p for p in providers if p.name == provider), None)

    if not provider_data:
        flash(request, f"OAuth provider '{provider}' is not configured.", "error")
        return RedirectResponse(url="/login", status_code=303)

    # Store provider and code verifier in session for callback
    request.session["oauth_provider"] = provider
    request.session["oauth_code_verifier"] = provider_data.code_verifier
    request.session["oauth_state"] = provider_data.state

    # Build the redirect URL (where provider will send user back)
    redirect_url = str(request.url_for("oauth2_callback", provider=provider))

    # PocketBase's auth_url already contains all necessary OAuth params
    # Just append our redirect_uri
    import urllib.parse
    auth_url = f"{provider_data.auth_url}{urllib.parse.quote(redirect_url, safe='')}"

    return RedirectResponse(url=auth_url, status_code=303)


@router.get("/auth/oauth2/{provider}/callback")
async def oauth2_callback(request: Request, provider: str):
    """Handles the OAuth2 callback after user authorizes."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if not code:
        flash(request, "OAuth authentication failed. No authorization code received.", "error")
        return RedirectResponse(url="/login", status_code=303)

    # Retrieve stored data from session
    code_verifier = request.session.get("oauth_code_verifier")
    stored_provider = request.session.get("oauth_provider")
    stored_state = request.session.get("oauth_state")

    if not code_verifier or stored_provider != provider:
        flash(request, "OAuth authentication failed. Invalid session state.", "error")
        return RedirectResponse(url="/login", status_code=303)

    # Verify state parameter to prevent CSRF
    if state != stored_state:
        flash(request, "OAuth authentication failed. State mismatch.", "error")
        return RedirectResponse(url="/login", status_code=303)

    # Build redirect URL for PocketBase
    redirect_url = str(request.url_for("oauth2_callback", provider=provider))

    # Authenticate with PocketBase
    auth_data = pocketbase_service.auth_with_oauth2(
        provider=provider,
        code=code,
        code_verifier=code_verifier,
        redirect_url=redirect_url
    )

    # Clean up session
    request.session.pop("oauth_code_verifier", None)
    request.session.pop("oauth_provider", None)
    request.session.pop("oauth_state", None)

    if not auth_data:
        flash(request, "OAuth authentication failed. Please try again.", "error")
        return RedirectResponse(url="/login", status_code=303)

    # Store auth data in session
    request.session["user_token"] = auth_data.token
    request.session["user_id"] = auth_data.record.id

    flash(request, f"Successfully logged in with {provider.title()}!", "success")
    return RedirectResponse(url="/dashboard", status_code=303)


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