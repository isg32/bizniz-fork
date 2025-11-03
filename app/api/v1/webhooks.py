# app/api/v1/webhooks.py

import stripe
import logging
from fastapi import APIRouter, Request, Header, HTTPException
from pocketbase.utils import ClientResponseError
from app.core.config import settings
from app.services.internal import pocketbase_service, email_service

router = APIRouter()
logger = logging.getLogger(__name__)

# --- Webhook Event Handlers ---


def _get_product_details_from_line_item(line_item) -> tuple[str, int]:
    """Helper to extract product name and coins from a Stripe line item object."""
    try:
        product = line_item.price.product
        product_name = product.name
        coins = int(product.metadata.get("coins", 0))
        return product_name, coins
    except (AttributeError, TypeError, ValueError) as e:
        logger.error(
            "WEBHOOK-HELPER: Could not parse product details. Error: %s",
            e,
            exc_info=True,
        )
        return "Unknown Product", 0


def handle_checkout_completed(session: dict):
    """
    Handles 'checkout.session.completed' event.
    - Fulfills the initial purchase (one-time or first subscription payment).
    - Links Stripe Customer ID and Subscription ID to the user.
    - Sends a welcome email for new subscriptions.
    """
    session_id = session.get("id")
    user_id = session.get("client_reference_id")
    stripe_customer_id = session.get("customer")

    logger.info(
        "WEBHOOK: Processing 'checkout.session.completed' for session '%s'. User ID: '%s'.",
        session_id,
        user_id,
    )

    if not user_id:
        logger.critical(
            "WEBHOOK: Missing client_reference_id in session '%s'. Cannot process.",
            session_id,
        )
        return

    user = pocketbase_service.get_user_by_id(user_id)
    if not user:
        logger.critical(
            "WEBHOOK: User with ID '%s' not found for session '%s'.",
            user_id,
            session_id,
        )
        return

    # --- CORRECTED LOGIC: Fulfill the order BEFORE updating user state ---
    # This prevents the user being marked as 'active' if coin addition fails.
    try:
        line_items = stripe.checkout.Session.list_line_items(
            session_id, limit=1, expand=["data.price.product"]
        )
        if not line_items.data:
            logger.warning(
                "WEBHOOK: No line items found for session '%s'. No fulfillment.",
                session_id,
            )
            # Stop processing, as this is unexpected for a completed session.
            return

        product_name, coins_to_add = _get_product_details_from_line_item(
            line_items.data[0]
        )
        description = f"Purchase: {product_name}"
        transaction_type = (
            "purchase" if session.get("mode") == "payment" else "subscription"
        )

        if coins_to_add > 0:
            pocketbase_service.add_coins(
                user_id,
                coins_to_add,
                description,
                session.get("payment_intent"),
                transaction_type,
            )
            logger.info(
                "WEBHOOK-SUCCESS: Added %d coins to user '%s' for '%s'.",
                coins_to_add,
                user_id,
                product_name,
            )
        else:
            logger.warning(
                "WEBHOOK: Product '%s' in session '%s' has zero 'coins' metadata.",
                product_name,
                session_id,
            )
    except stripe.StripeError as e:
        logger.critical(
            "WEBHOOK: FULFILLMENT FAILED for session '%s'. User '%s' has paid but received NO coins. MANUAL INTERVENTION REQUIRED. Stripe Error: %s",
            session_id,
            user_id,
            e,
            exc_info=True,
        )
        # Raise an exception to tell Stripe to retry the webhook later.
        raise HTTPException(status_code=500, detail="Fulfillment failed, will retry.")
    except Exception as e:
        logger.critical(
            "WEBHOOK: Unexpected error during fulfillment for session '%s'. Error: %s",
            session_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail="Internal fulfillment error, will retry."
        )

    # --- If fulfillment was successful, now update the user record ---
    update_data = {}
    if stripe_customer_id:
        update_data["stripe_customer_id"] = stripe_customer_id

    if session.get("mode") == "subscription":
        stripe_subscription_id = session.get("subscription")
        update_data["stripe_subscription_id"] = stripe_subscription_id
        update_data["subscription_status"] = "active"
        update_data["active_plan_name"] = product_name  # We already have this!

        dashboard_url = f"{settings.FRONTEND_URL}/dashboard"
        email_service.send_subscription_started_email(
            user.email, user.name, product_name, dashboard_url
        )
        logger.info(
            "WEBHOOK: Subscription start email sent to %s for plan '%s'.",
            user.email,
            product_name,
        )

    if update_data:
        success, _ = pocketbase_service.update_user(user_id, update_data)
        if success:
            logger.info(
                "WEBHOOK: User '%s' updated successfully with: %s", user_id, update_data
            )


def handle_invoice_succeeded(invoice: dict):
    if invoice.get("billing_reason") != "subscription_cycle":
        logger.info(
            "WEBHOOK: Ignoring 'invoice.payment_succeeded' for reason: '%s'.",
            invoice.get("billing_reason"),
        )
        return

    stripe_customer_id = invoice.get("customer")
    invoice_id = invoice.get("id")
    logger.info(
        "WEBHOOK: Processing 'invoice.payment_succeeded' for invoice '%s'.", invoice_id
    )

    if not stripe_customer_id:
        return

    user = pocketbase_service.get_user_by_stripe_customer_id(stripe_customer_id)
    if not user:
        logger.warning(
            "WEBHOOK: Received recurring payment for unknown Stripe customer '%s'.",
            stripe_customer_id,
        )
        return

    try:
        # Invoice line items already have the expanded product data
        line_item = invoice.get("lines", {}).get("data", [{}])[0]
        product_name, coins_to_add = _get_product_details_from_line_item(line_item)

        if coins_to_add > 0:
            description = f"Subscription Renewal: {product_name}"
            pocketbase_service.add_coins(
                user.id, coins_to_add, description, invoice.get("charge"), "renewal"
            )
            email_service.send_renewal_receipt_email(
                user.email, user.name, coins_to_add, product_name
            )
            logger.info(
                "WEBHOOK-SUCCESS: Fulfilled renewal for user '%s' from invoice '%s'.",
                user.id,
                invoice_id,
            )
        else:
            logger.warning(
                "WEBHOOK: Product in renewal invoice '%s' has zero 'coins' metadata.",
                invoice_id,
            )
    except Exception as e:
        logger.critical(
            "WEBHOOK: Failed to fulfill renewal for invoice '%s'. Error: %s",
            invoice_id,
            e,
            exc_info=True,
        )


def handle_subscription_updated(subscription: dict):
    stripe_subscription_id = subscription.get("id")
    stripe_customer_id = subscription.get("customer")
    logger.info(
        "WEBHOOK: Processing 'customer.subscription.updated' for sub '%s'.",
        stripe_subscription_id,
    )

    user = pocketbase_service.get_user_by_stripe_customer_id(stripe_customer_id)
    if not user:
        logger.warning(
            "WEBHOOK: No user found for Stripe customer '%s' on subscription update.",
            stripe_customer_id,
        )
        return

    update_data = {}

    # --- NEW: Handle plan changes (upgrades/downgrades) ---
    try:
        items = subscription.get("items", {}).get("data", [])
        if items:
            # The product object is nested within the price object on the subscription item
            product = items[0].get("price", {}).get("product", {})
            new_plan_name = getattr(product, "name", None)
            if new_plan_name and new_plan_name != user.active_plan_name:
                update_data["active_plan_name"] = new_plan_name
                logger.info(
                    "WEBHOOK: Plan for user '%s' changed to '%s'.",
                    user.id,
                    new_plan_name,
                )
    except Exception as e:
        logger.error(
            "WEBHOOK: Could not parse product details from subscription update '%s'. Error: %s",
            stripe_subscription_id,
            e,
        )

    # --- Existing cancellation and reactivation logic ---
    if subscription.get("cancel_at_period_end"):
        if user.subscription_status != "canceling":
            update_data["subscription_status"] = "canceling"
            portal_url = f"{settings.FRONTEND_URL}/dashboard/billing"
            email_service.send_subscription_cancelled_email(
                user.email, user.name, user.active_plan_name or "your plan", portal_url
            )
            logger.info(
                "WEBHOOK: Subscription '%s' for user '%s' set to cancel. Email sent.",
                stripe_subscription_id,
                user.id,
            )
    elif subscription.get("status") == "active":
        # This handles both reactivation and confirms 'active' status after an upgrade.
        if user.subscription_status != "active":
            update_data["subscription_status"] = "active"
            logger.info(
                "WEBHOOK: Subscription '%s' for user '%s' status set to active.",
                stripe_subscription_id,
                user.id,
            )

    if update_data:
        pocketbase_service.update_user(user.id, update_data)


def handle_subscription_deleted(subscription: dict):
    stripe_subscription_id = subscription.get("id")
    logger.info(
        "WEBHOOK: Processing 'customer.subscription.deleted' for sub '%s'.",
        stripe_subscription_id,
    )
    user = pocketbase_service.get_user_by_stripe_subscription_id(stripe_subscription_id)
    if not user:
        logger.warning(
            "WEBHOOK: No user found with subscription ID '%s'.", stripe_subscription_id
        )
        return
    update_data = {
        "subscription_status": "cancelled",
        "active_plan_name": None,
        "stripe_subscription_id": None,
    }
    pocketbase_service.update_user(user.id, update_data)
    logger.info(
        "WEBHOOK-SUCCESS: Subscription for user '%s' fully ended. Status set to 'cancelled'.",
        user.id,
    )


def handle_customer_created(customer: dict):
    customer_id = customer.get("id")
    customer_email = customer.get("email")
    logger.info(
        "WEBHOOK: Processing 'customer.created' for customer '%s'.", customer_id
    )
    if not customer_email:
        logger.warning(
            "WEBHOOK: Customer '%s' created without an email. Cannot link.", customer_id
        )
        return
    user = pocketbase_service.get_user_by_email(customer_email)
    if user and not user.stripe_customer_id:
        pocketbase_service.update_user(user.id, {"stripe_customer_id": customer_id})
        logger.info(
            "WEBHOOK: Linked new Stripe Customer '%s' to user '%s' via email.",
            customer_id,
            user.id,
        )


# --- Main Webhook Route ---

EVENT_HANDLERS = {
    "checkout.session.completed": handle_checkout_completed,
    "invoice.payment_succeeded": handle_invoice_succeeded,
    "customer.subscription.deleted": handle_subscription_deleted,
    # This event needs to have the product expanded from the Stripe dashboard settings
    "customer.subscription.updated": handle_subscription_updated,
    "customer.created": handle_customer_created,
}


@router.post("/stripe", include_in_schema=False)
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    """Listens for and processes all incoming events from Stripe."""
    try:
        payload = await request.body()
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.error("STRIPE-WEBHOOK: Invalid payload. Error: %s", e)
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")
    except stripe.error.SignatureVerificationError as e:
        logger.error(
            "STRIPE-WEBHOOK: Webhook signature verification failed. Error: %s", e
        )
        raise HTTPException(status_code=400, detail=f"Webhook signature error: {e}")

    event_id = event.get("id")
    event_type = event.get("type")

    try:
        pocketbase_service.admin_pb.collection("processed_stripe_events").get_one(
            event_id
        )
        logger.warning(
            "STRIPE-WEBHOOK: Duplicate event '%s' (ID: %s) received. Ignoring.",
            event_type,
            event_id,
        )
        return {"status": "duplicate ignored"}
    except ClientResponseError as e:
        if e.status != 404:
            logger.error(
                "STRIPE-WEBHOOK: DB error checking event idempotency for '%s'. Error: %s",
                event_id,
                e,
            )
            raise HTTPException(
                status_code=500, detail="Could not verify event idempotency."
            )

    handler = EVENT_HANDLERS.get(event_type)
    if handler:
        logger.info(
            "STRIPE-WEBHOOK: Received event: '%s' (ID: %s). Routing to handler.",
            event_type,
            event_id,
        )
        try:
            # For subscription updates, we need to expand the product data directly
            if event_type == "customer.subscription.updated":
                subscription = stripe.Subscription.retrieve(
                    event["data"]["object"]["id"],
                    expand=["items.data.price.product"],
                )
                handler(subscription)
            else:
                handler(event["data"]["object"])

            try:
                pocketbase_service.admin_pb.collection(
                    "processed_stripe_events"
                ).create({"id": event_id})
            except Exception as e_create:
                logger.critical(
                    "STRIPE-WEBHOOK: CRITICAL - Processed event '%s' but FAILED to record it. Manual check required! Error: %s",
                    event_id,
                    e_create,
                )
        except HTTPException:
            # Re-raise the HTTPException from the handler to send a 500 to Stripe
            raise
        except Exception as e:
            logger.critical(
                "STRIPE-WEBHOOK: Unhandled exception in handler for '%s'. Event ID: %s. Error: %s",
                event_type,
                event_id,
                e,
                exc_info=True,
            )
            raise HTTPException(
                status_code=500, detail="Internal server error in event handler."
            )
    else:
        logger.info("STRIPE-WEBHOOK: Ignoring unhandled event type '%s'.", event_type)

    return {"status": "received"}
