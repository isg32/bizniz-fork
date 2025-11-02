# app/api/v1/__init__.py

from fastapi import APIRouter
from app.api.v1 import auth, users, payments, webhooks

api_router = APIRouter()

# --- Public API Endpoints ---
# These are endpoints that the frontend application will call.
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(payments.router, prefix="/payments", tags=["Payments"])

# --- Internal Webhook Endpoints ---
# These endpoints are not meant for the frontend, but for external services like Stripe.
# They are included here for organizational purposes under the v1 API.
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
