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
            f"WEBHOOK-HELPER-ERROR: Could not parse product details. Error: {e}",
            exc_info=True,
        )
        return "Unknown Product", 0


def handle_checkout_completed(session: dict):
    """
    Handles 'checkout.session.completed' event.
    - Links Stripe Customer ID to the user.
    - Fulfills the initial purchase (one-time or first subscription payment).
    - Sends a welcome email for new subscriptions.
    """
    session_id = session.get("id")
    user_id = session.get("client_reference_id")
    stripe_customer_id = session.get("customer")

    logger.info(
        f"WEBHOOK: Processing 'checkout.session.completed' for session '{session_id}'. User ID: '{user_id}'."
    )

    if not user_id:
        logger.error(
            f"WEBHOOK-FATAL: Missing client_reference_id in session '{session_id}'. Cannot process."
        )
        return

    user = pocketbase_service.get_user_by_id(user_id)
    if not user:
        logger.error(
            f"WEBHOOK-FATAL: User with ID '{user_id}' not found for session '{session_id}'."
        )
        return

    update_data = {}
    if stripe_customer_id:
        update_data["stripe_customer_id"] = stripe_customer_id

    if session.get("mode") == "subscription":
        stripe_subscription_id = session.get("subscription")
        update_data["stripe_subscription_id"] = stripe_subscription_id
        update_data["subscription_status"] = "active"
        plan_name = "Unknown Plan"
        try:
            subscription = stripe.Subscription.retrieve(
                stripe_subscription_id, expand=["items.data.price.product"]
            )
            items = subscription.get("items", {}).get("data", [])
            if items:
                product = items[0].get("price", {}).get("product", {})
                plan_name = getattr(product, "name", "Unknown Plan")
                update_data["active_plan_name"] = plan_name

            dashboard_url = f"{settings.FRONTEND_URL}/dashboard"
            email_service.send_subscription_started_email(
                user.email, user.name, plan_name, dashboard_url
            )
            logger.info(
                f"WEBHOOK: Subscription start email sent to {user.email} for plan '{plan_name}'."
            )

        except stripe.StripeError as e:
            logger.error(
                f"WEBHOOK-API-ERROR: Stripe API failed to retrieve subscription '{stripe_subscription_id}'. Error: {e}"
            )

    if update_data:
        success, _ = pocketbase_service.update_user(user_id, update_data)
        if success:
            logger.info(
                f"WEBHOOK: User '{user_id}' updated successfully with: {update_data}"
            )

    try:
        line_items = stripe.checkout.Session.list_line_items(
            session_id, limit=1, expand=["data.price.product"]
        )
        if not line_items.data:
            logger.warning(
                f"WEBHOOK: No line items found for session '{session_id}'. No fulfillment."
            )
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
                f"WEBHOOK-SUCCESS: Added {coins_to_add} coins to user '{user_id}' for '{product_name}'."
            )
        else:
            logger.warning(
                f"WEBHOOK-WARN: Product '{product_name}' in session '{session_id}' has zero 'coins' metadata."
            )
    except stripe.StripeError as e:
        logger.error(
            f"WEBHOOK-FATAL: Stripe API failed to list line items for session '{session_id}'. Error: {e}",
            exc_info=True,
        )
    except Exception as e:
        logger.error(
            f"WEBHOOK-FATAL: An unexpected error occurred during fulfillment for session '{session_id}'. Error: {e}",
            exc_info=True,
        )


def handle_invoice_succeeded(invoice: dict):
    if invoice.get("billing_reason") != "subscription_cycle":
        logger.info(
            f"WEBHOOK: Ignoring 'invoice.payment_succeeded' for reason: '{invoice.get('billing_reason')}'."
        )
        return

    stripe_customer_id = invoice.get("customer")
    invoice_id = invoice.get("id")
    logger.info(
        f"WEBHOOK: Processing 'invoice.payment_succeeded' for invoice '{invoice_id}'."
    )

    if not stripe_customer_id:
        return

    user = pocketbase_service.get_user_by_stripe_customer_id(stripe_customer_id)
    if not user:
        logger.warning(
            f"WEBHOOK-WARN: Received recurring payment for unknown Stripe customer '{stripe_customer_id}'."
        )
        return

    try:
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
                f"WEBHOOK-SUCCESS: Fulfilled renewal for user '{user.id}' from invoice '{invoice_id}'."
            )
        else:
            logger.warning(
                f"WEBHOOK-WARN: Product in renewal invoice '{invoice_id}' has zero 'coins' metadata."
            )
    except Exception as e:
        logger.error(
            f"WEBHOOK-FATAL: Failed to fulfill renewal for invoice '{invoice_id}'. Error: {e}",
            exc_info=True,
        )


def handle_subscription_updated(subscription: dict):
    stripe_subscription_id = subscription.get("id")
    stripe_customer_id = subscription.get("customer")
    logger.info(
        f"WEBHOOK: Processing 'customer.subscription.updated' for sub '{stripe_subscription_id}'."
    )

    user = pocketbase_service.get_user_by_stripe_customer_id(stripe_customer_id)
    if not user:
        logger.warning(
            f"WEBHOOK-WARN: No user found for Stripe customer '{stripe_customer_id}' on subscription update."
        )
        return

    update_data = {}
    if subscription.get("cancel_at_period_end"):
        if user.subscription_status != "canceling":
            update_data["subscription_status"] = "canceling"

            portal_url = f"{settings.FRONTEND_URL}/dashboard/billing"  # A more specific URL is better
            email_service.send_subscription_cancelled_email(
                user.email, user.name, user.active_plan_name or "your plan", portal_url
            )
            logger.info(
                f"WEBHOOK: Subscription '{stripe_subscription_id}' for user '{user.id}' set to cancel. Email sent."
            )
    elif subscription.get("status") == "active" and not subscription.get(
        "cancel_at_period_end"
    ):
        if user.subscription_status == "canceling":
            update_data["subscription_status"] = "active"
            logger.info(
                f"WEBHOOK: Subscription '{stripe_subscription_id}' for user '{user.id}' was reactivated."
            )

    if update_data:
        pocketbase_service.update_user(user.id, update_data)


def handle_subscription_deleted(subscription: dict):
    stripe_subscription_id = subscription.get("id")
    logger.info(
        f"WEBHOOK: Processing 'customer.subscription.deleted' for sub '{stripe_subscription_id}'."
    )
    user = pocketbase_service.get_user_by_stripe_subscription_id(stripe_subscription_id)
    if not user:
        logger.warning(
            f"WEBHOOK-WARN: No user found with subscription ID '{stripe_subscription_id}'."
        )
        return
    update_data = {
        "subscription_status": "cancelled",
        "active_plan_name": None,
        "stripe_subscription_id": None,
    }
    pocketbase_service.update_user(user.id, update_data)
    logger.info(
        f"WEBHOOK-SUCCESS: Subscription for user '{user.id}' fully ended. Status set to 'cancelled'."
    )


def handle_customer_created(customer: dict):
    customer_id = customer.get("id")
    customer_email = customer.get("email")
    logger.info(f"WEBHOOK: Processing 'customer.created' for customer '{customer_id}'.")
    if not customer_email:
        logger.warning(
            f"WEBHOOK: Customer '{customer_id}' created without an email. Cannot link."
        )
        return
    user = pocketbase_service.get_user_by_email(customer_email)
    if user and not user.stripe_customer_id:
        pocketbase_service.update_user(user.id, {"stripe_customer_id": customer_id})
        logger.info(
            f"WEBHOOK: Linked new Stripe Customer '{customer_id}' to user '{user.id}' via email."
        )


# --- Main Webhook Route ---

EVENT_HANDLERS = {
    "checkout.session.completed": handle_checkout_completed,
    "invoice.payment_succeeded": handle_invoice_succeeded,
    "customer.subscription.deleted": handle_subscription_deleted,
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
        logger.error(f"STRIPE-WEBHOOK: Invalid payload. Error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")
    except stripe.error.SignatureVerificationError as e:
        logger.error(
            f"STRIPE-WEBHOOK: Webhook signature verification failed. Error: {e}"
        )
        raise HTTPException(status_code=400, detail=f"Webhook signature error: {e}")

    event_id = event.get("id")
    event_type = event.get("type")

    try:
        pocketbase_service.admin_pb.collection("processed_stripe_events").get_one(
            event_id
        )
        logger.warning(
            f"STRIPE-WEBHOOK: Duplicate event '{event_type}' (ID: {event_id}) received. Ignoring."
        )
        return {"status": "duplicate ignored"}
    except ClientResponseError as e:
        if e.status != 404:
            logger.error(
                f"STRIPE-WEBHOOK: DB error checking event idempotency for '{event_id}'. Error: {e}"
            )
            raise HTTPException(
                status_code=500, detail="Could not verify event idempotency."
            )

    handler = EVENT_HANDLERS.get(event_type)
    if handler:
        logger.info(
            f"STRIPE-WEBHOOK: Received event: '{event_type}' (ID: {event_id}). Routing to handler."
        )
        try:
            handler(event["data"]["object"])
            try:
                pocketbase_service.admin_pb.collection(
                    "processed_stripe_events"
                ).create({"id": event_id})
            except Exception as e_create:
                logger.critical(
                    f"STRIPE-WEBHOOK: CRITICAL - Processed event '{event_id}' but FAILED to record it. Manual check required! Error: {e_create}"
                )
        except Exception as e:
            logger.critical(
                f"STRIPE-WEBHOOK: Unhandled exception in handler for '{event_type}'. Event ID: {event_id}. Error: {e}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=500, detail="Internal server error in event handler."
            )
    else:
        logger.info(f"STRIPE-WEBHOOK: Ignoring unhandled event type '{event_type}'.")

    return {"status": "received"}
