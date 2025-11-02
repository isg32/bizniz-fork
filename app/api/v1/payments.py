# app/api/v1/payments.py

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.services.internal import stripe_service
from app.core.dependencies import get_current_api_user
from app.schemas.user import User as UserSchema
from app.schemas.msg import Msg

router = APIRouter()

# --- Schemas for API Requests ---


class CheckoutSessionRequest(BaseModel):
    price_id: str = Field(..., description="The ID of the Stripe Price object.")
    mode: str = Field(
        ...,
        pattern="^(payment|subscription)$",
        description="The mode of the checkout session ('payment' or 'subscription').",
    )
    success_url: str = Field(
        ..., description="The URL to redirect to on successful payment."
    )
    cancel_url: str = Field(
        ..., description="The URL to redirect to on cancelled payment."
    )


class PortalSessionRequest(BaseModel):
    return_url: str = Field(
        ..., description="The URL to redirect to after leaving the billing portal."
    )


# --- Schemas for API Responses ---


class Product(BaseModel):
    price_id: str
    name: str
    description: str | None = None
    price: float
    currency: str
    coins: str  # Stored as string metadata in Stripe


class ProductsResponse(BaseModel):
    subscription_plans: list[Product]
    one_time_packs: list[Product]


class CheckoutSessionResponse(BaseModel):
    session_id: str
    url: str


class PortalSessionResponse(BaseModel):
    url: str


# --- API Endpoints for Payments ---


@router.get(
    "/products", response_model=ProductsResponse, summary="Get all active products"
)
async def get_products():
    """
    Retrieves all active subscription plans and one-time purchase packs from Stripe.
    The frontend uses this to display the pricing page.
    """
    try:
        subscription_plans, one_time_packs = (
            stripe_service.get_all_active_products_and_prices()
        )
        return ProductsResponse(
            subscription_plans=[Product.model_validate(p) for p in subscription_plans],
            one_time_packs=[Product.model_validate(p) for p in one_time_packs],
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not retrieve products from payment provider: {e}",
        )


@router.post(
    "/checkout-session",
    response_model=CheckoutSessionResponse,
    summary="Create a checkout session",
)
async def create_checkout_session(
    checkout_request: CheckoutSessionRequest,
    current_user: UserSchema = Depends(get_current_api_user),
):
    """
    Creates a Stripe Checkout session for the authenticated user.
    The frontend provides success/cancel URLs and redirects the user to the returned `url`.
    """
    # Business Logic Checks
    if checkout_request.mode == "subscription":
        if current_user.subscription_status in ["active", "canceling"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have an active subscription. Please manage it from the billing portal.",
            )
    if checkout_request.mode == "payment":
        if current_user.subscription_status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="One-time purchases are only available for users with an active subscription.",
            )

    # Create Session
    try:
        session = stripe_service.create_checkout_session(
            price_id=checkout_request.price_id,
            user_id=current_user.id,
            success_url=checkout_request.success_url,
            cancel_url=checkout_request.cancel_url,
            mode=checkout_request.mode,
        )
        if not session or not session.url:
            raise HTTPException(status_code=500, detail="Failed to create session.")

        return CheckoutSessionResponse(session_id=session.id, url=session.url)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not connect to payment provider: {e}",
        )


@router.post(
    "/customer-portal",
    response_model=PortalSessionResponse,
    summary="Create a customer portal session",
)
async def create_customer_portal_session(
    portal_request: PortalSessionRequest,
    current_user: UserSchema = Depends(get_current_api_user),
):
    """
    Creates a Stripe Customer Billing Portal session for the authenticated user.
    The frontend provides the return_url and redirects the user to the portal.
    """
    if not current_user.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No billing information found for this user.",
        )
    try:
        portal_session = stripe_service.create_customer_portal_session(
            stripe_customer_id=current_user.stripe_customer_id,
            return_url=portal_request.return_url,
        )
        if not portal_session or not portal_session.url:
            raise HTTPException(
                status_code=500, detail="Failed to create portal session."
            )
        return PortalSessionResponse(url=portal_session.url)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not connect to billing provider: {e}",
        )


@router.post("/subscriptions/cancel", response_model=Msg, summary="Cancel subscription")
async def cancel_subscription(current_user: UserSchema = Depends(get_current_api_user)):
    """
    Requests to cancel the user's active subscription at the end of the current billing period.
    """
    if not current_user.stripe_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found to cancel.",
        )
    if current_user.subscription_status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Subscription cannot be cancelled as its status is '{current_user.subscription_status}'.",
        )
    success = stripe_service.cancel_subscription(current_user.stripe_subscription_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to cancel subscription with the payment provider.",
        )
    return {
        "msg": "Your subscription has been scheduled for cancellation at the end of the current billing period."
    }


@router.post(
    "/subscriptions/reactivate", response_model=Msg, summary="Reactivate subscription"
)
async def reactivate_subscription(
    current_user: UserSchema = Depends(get_current_api_user),
):
    """
    Reactivates a subscription that was previously scheduled for cancellation.
    """
    if not current_user.stripe_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription found to reactivate.",
        )
    if current_user.subscription_status != "canceling":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Subscription can only be reactivated if it is currently in 'canceling' status.",
        )
    success = stripe_service.reactivate_subscription(
        current_user.stripe_subscription_id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to reactivate subscription with the payment provider.",
        )
    return {"msg": "Your subscription has been successfully reactivated."}
