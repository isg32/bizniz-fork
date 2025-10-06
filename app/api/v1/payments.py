import stripe
from fastapi import APIRouter, Request, Header, HTTPException
from app.core.config import settings
from app.services import pocketbase_service, email_service

router = APIRouter()

# --- Webhook Event Handlers ---

def _get_product_details_from_line_item(line_item) -> tuple:
    """Helper to extract product name and coins from a line item object."""
    try:
        product = line_item.price.product
        product_name = product.name
        coins = int(product.metadata.get('coins', 0))
        return product_name, coins
    except (AttributeError, TypeError, ValueError):
        return "Unknown Product", 0

def handle_checkout_completed(session: dict):
    """
    Handles the 'checkout.session.completed' event.
    - Links Stripe Customer ID to the user.
    - Fulfills the initial purchase (one-time or first subscription payment).
    """
    user_id = session.get('client_reference_id')
    stripe_customer_id = session.get('customer')
    if not all([user_id, stripe_customer_id]):
        print(f"WEBHOOK-ERROR: Missing user_id or customer_id in session {session.get('id')}.")
        return

    # --- Link User to Stripe Customer ID ---
    user = pocketbase_service.get_user_by_id(user_id)
    if not user:
        print(f"WEBHOOK-ERROR: User with ID {user_id} not found.")
        return
        
    update_data = {"stripe_customer_id": stripe_customer_id}

    # If it's a new subscription, store the subscription details
    if session.get('mode') == 'subscription':
        stripe_subscription_id = session.get('subscription')
        update_data['stripe_subscription_id'] = stripe_subscription_id
        update_data['subscription_status'] = 'active'
        # We need to fetch the plan name for the user's dashboard
        try:
            sub_items = stripe.Subscription.retrieve(stripe_subscription_id, expand=['items.data.price.product']).items.data
            if sub_items:
                update_data['active_plan_name'] = sub_items[0].price.product.name
        except Exception as e:
            print(f"WEBHOOK-API-ERROR: Could not retrieve subscription details for {stripe_subscription_id}. Error: {e}")

    pocketbase_service.update_user(user_id, update_data)
    print(f"WEBHOOK-INFO: Linked user {user_id} with Stripe customer {stripe_customer_id}.")

    # --- Fulfill the Purchase ---
    try:
        line_items = stripe.checkout.Session.list_line_items(session.id, limit=1, expand=['data.price.product'])
        if not line_items.data: return

        product_name, coins_to_add = _get_product_details_from_line_item(line_items.data[0])
        description = f"Purchase of {product_name}"
        transaction_type = "purchase" if session.get('mode') == 'payment' else "renewal"

        if coins_to_add > 0:
            pocketbase_service.add_coins(user_id, coins_to_add, description, session.get('payment_intent'), transaction_type)
        else:
            print(f"WEBHOOK-WARN: Product in session {session.id} has no 'coins' metadata.")
    except Exception as e:
        print(f"WEBHOOK-API-ERROR: Failed to fulfill purchase for session {session.get('id')}: {e}")

def handle_invoice_succeeded(invoice: dict):
    """
    Handles 'invoice.payment_succeeded' for recurring subscription renewals.
    """
    if invoice.get('billing_reason') != 'subscription_cycle':
        # We only care about automatic renewals, not the initial payment (handled by checkout)
        return

    stripe_customer_id = invoice.get('customer')
    if not stripe_customer_id: return

    user = pocketbase_service.get_user_by_stripe_customer_id(stripe_customer_id)
    if not user:
        print(f"WEBHOOK-WARN: Received recurring payment for unknown Stripe customer {stripe_customer_id}.")
        return
    
    # --- Fulfill the Renewal ---
    try:
        line_item = invoice.get('lines', {}).get('data', [{}])[0]
        product_name, coins_to_add = _get_product_details_from_line_item(line_item)
        description = f"Subscription renewal: {product_name}"
        
        if coins_to_add > 0:
            pocketbase_service.add_coins(user.id, coins_to_add, description, invoice.get('charge'), "renewal")
            # --- Send Receipt Email ---
            email_service.send_renewal_receipt_email(user.email, user.name, coins_to_add, product_name)
        else:
            print(f"WEBHOOK-WARN: Product in invoice {invoice.id} has no 'coins' metadata.")
    except Exception as e:
         print(f"WEBHOOK-API-ERROR: Failed to fulfill renewal for invoice {invoice.get('id')}: {e}")

def handle_subscription_deleted(subscription: dict):
    """
    Handles 'customer.subscription.deleted' when a subscription is cancelled or ends.
    """
    stripe_subscription_id = subscription.get('id')
    user = pocketbase_service.get_user_by_stripe_customer_id(subscription.get('customer'))
    
    if user and user.stripe_subscription_id == stripe_subscription_id:
        update_data = {
            "subscription_status": "cancelled",
            "active_plan_name": None
        }
        pocketbase_service.update_user(user.id, update_data)
        print(f"WEBHOOK-SUCCESS: Marked subscription as 'cancelled' for user {user.id}.")

# --- Main Webhook Route ---

EVENT_HANDLERS = {
    'checkout.session.completed': handle_checkout_completed,
    'invoice.payment_succeeded': handle_invoice_succeeded,
    'customer.subscription.deleted': handle_subscription_deleted,
}

@router.post("/stripe-webhook", include_in_schema=False)
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    """Listens for and processes all incoming events from Stripe."""
    try:
        payload = await request.body()
        event = stripe.Webhook.construct_event(payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {e}")

    # Get the appropriate handler for the event type
    handler = EVENT_HANDLERS.get(event['type'])
    
    if handler:
        print(f"STRIPE-WEBHOOK: Received and processing event: '{event['type']}' (ID: {event['id']})")
        handler(event['data']['object'])
    else:
        print(f"STRIPE-WEBHOOK: Ignoring unhandled event type '{event['type']}'.")
        
    return {"status": "received"}