# app/services/internal/stripe_service.py

import stripe
import logging
from app.core.config import settings
from app.services.internal import pocketbase_service

# --- Initialization ---
stripe.api_key = settings.STRIPE_API_KEY
logger = logging.getLogger(__name__)


# --- Product Retrieval ---
def get_all_active_products_and_prices() -> tuple[list[dict], list[dict]]:
    """
    Fetches all active products from Stripe scoped to this application.
    Separates them into one-time packs and recurring subscription plans.
    """
    APP_ID = "bizniz_ai_v1"  # This should match the 'app_id' metadata in your Stripe Products.

    try:
        logger.info("STRIPE-SVC: Fetching active products...")
        products_response = stripe.Product.search(
            query=f"active:'true' AND metadata['app_id']:'{APP_ID}'",
            expand=["data.default_price"],
        )
        products = products_response.data

        one_time_packs = []
        subscription_plans = []

        for product in products:
            price = product.default_price
            if not price or not price.active:
                logger.warning(
                    f"STRIPE-SVC: Product '{product.name}' ({product.id}) skipped due to missing or inactive price."
                )
                continue

            item = {
                "price_id": price.id,
                "name": product.name,
                "description": product.description,
                "price": price.unit_amount / 100,
                "currency": price.currency.upper(),
                "coins": product.metadata.get("coins", "0"),
            }

            if price.type == "recurring":
                subscription_plans.append(item)
            else:
                one_time_packs.append(item)

        # Sort by price ascending
        one_time_packs.sort(key=lambda x: x["price"])
        subscription_plans.sort(key=lambda x: x["price"])

        logger.info(
            f"STRIPE-SVC: Found {len(subscription_plans)} subscription plans and {len(one_time_packs)} one-time packs."
        )
        return subscription_plans, one_time_packs

    except stripe.StripeError as e:
        logger.error(
            f"STRIPE-SVC: Stripe API error fetching products. Error: {e}", exc_info=True
        )
        raise e  # Re-raise to be handled by the API layer
    except Exception as e:
        logger.error(
            f"STRIPE-SVC: An unexpected error occurred while fetching products. Error: {e}",
            exc_info=True,
        )
        raise e


# --- Session Creation ---
def create_checkout_session(
    price_id: str, user_id: str, success_url: str, cancel_url: str, mode: str
):
    """
    Creates a Stripe Checkout session for a given price ID and user.
    Now requires explicit success/cancel URLs from the frontend.
    """
    try:
        logger.info(
            f"STRIPE-SVC: Creating checkout session for user '{user_id}' with price '{price_id}'."
        )
        user = pocketbase_service.get_user_by_id(user_id)
        if not user:
            logger.error(
                f"STRIPE-SVC: Cannot create session for non-existent user '{user_id}'."
            )
            return None

        session_params = {
            "payment_method_types": ["card"],
            "line_items": [{"price": price_id, "quantity": 1}],
            "mode": mode,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": user_id,
        }

        # Associate with existing Stripe customer or provide email for a new one
        if user and hasattr(user, "stripe_customer_id") and user.stripe_customer_id:
            session_params["customer"] = user.stripe_customer_id
            logger.info(
                f"STRIPE-SVC: Associating session with existing Stripe Customer ID: {user.stripe_customer_id}"
            )
        elif user:
            session_params["customer_email"] = user.email
            logger.info(
                f"STRIPE-SVC: Associating session with user email: {user.email}"
            )

        return stripe.checkout.Session.create(**session_params)

    except stripe.StripeError as e:
        logger.error(
            f"STRIPE-SVC: Stripe API error creating checkout session for user '{user_id}'. Error: {e}",
            exc_info=True,
        )
        raise e
    except Exception as e:
        logger.error(
            f"STRIPE-SVC: An unexpected error occurred during session creation for user '{user_id}'. Error: {e}",
            exc_info=True,
        )
        raise e


def create_customer_portal_session(stripe_customer_id: str, return_url: str):
    """
    Creates a Stripe Customer Portal session for a user to manage their subscription.
    Now requires an explicit return_url from the frontend.
    """
    try:
        logger.info(
            f"STRIPE-SVC: Creating customer portal session for customer '{stripe_customer_id}'."
        )
        return stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url,
        )
    except stripe.StripeError as e:
        logger.error(
            f"STRIPE-SVC: Stripe API error creating customer portal for '{stripe_customer_id}'. Error: {e}",
            exc_info=True,
        )
        raise e
    except Exception as e:
        logger.error(
            f"STRIPE-SVC: An unexpected error occurred during portal creation for '{stripe_customer_id}'. Error: {e}",
            exc_info=True,
        )
        raise e


# --- Subscription Management ---
def cancel_subscription(stripe_subscription_id: str) -> bool:
    """Cancels a Stripe subscription at the end of the billing period."""
    try:
        stripe.Subscription.modify(stripe_subscription_id, cancel_at_period_end=True)
        logger.info(
            f"STRIPE-SVC: Successfully set subscription '{stripe_subscription_id}' to cancel at period end."
        )
        return True
    except stripe.StripeError as e:
        logger.error(
            f"STRIPE-SVC: Stripe API error cancelling subscription '{stripe_subscription_id}'. Error: {e}",
            exc_info=True,
        )
        return False


def reactivate_subscription(stripe_subscription_id: str) -> bool:
    """Reactivates a Stripe subscription that was set to cancel at period end."""
    try:
        stripe.Subscription.modify(stripe_subscription_id, cancel_at_period_end=False)
        logger.info(
            f"STRIPE-SVC: Successfully reactivated subscription '{stripe_subscription_id}'."
        )
        return True
    except stripe.StripeError as e:
        logger.error(
            f"STRIPE-SVC: Stripe API error reactivating subscription '{stripe_subscription_id}'. Error: {e}",
            exc_info=True,
        )
        return False
