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

    print(f"WEBHOOK-DEBUG: Session ID: {session.get('id')}")
    print(f"WEBHOOK-DEBUG: client_reference_id: {user_id}")
    print(f"WEBHOOK-DEBUG: customer: {stripe_customer_id}")
    print(f"WEBHOOK-DEBUG: mode: {session.get('mode')}")

    if not user_id:
        print(f"WEBHOOK-ERROR: Missing client_reference_id in session {session.get('id')}.")
        return

    # --- Get User ---
    user = pocketbase_service.get_user_by_id(user_id)
    if not user:
        print(f"WEBHOOK-ERROR: User with ID {user_id} not found.")
        return

    # --- Handle Customer ID ---
    # For new users, customer might be None initially, so we retrieve it from Stripe
    if not stripe_customer_id:
        # Try to get customer from customer_details or wait for customer.created event
        customer_email = session.get('customer_details', {}).get('email') or session.get('customer_email')
        print(f"WEBHOOK-INFO: No customer ID in session, but found email: {customer_email}")

        # We can still fulfill the order without immediately linking the customer
        # The customer.created webhook will handle the linking
        stripe_customer_id = None

    # Update user with stripe_customer_id if we have it
    update_data = {}
    if stripe_customer_id:
        update_data["stripe_customer_id"] = stripe_customer_id
        print(f"WEBHOOK-INFO: Linking user {user_id} with Stripe customer {stripe_customer_id}.")

    # If it's a new subscription, store the subscription details
    if session.get('mode') == 'subscription':
        stripe_subscription_id = session.get('subscription')
        update_data['stripe_subscription_id'] = stripe_subscription_id
        update_data['subscription_status'] = 'active'
        # We need to fetch the plan name for the user's dashboard
        try:
            subscription = stripe.Subscription.retrieve(stripe_subscription_id, expand=['items.data.price.product'])
            # Access items - it could be a list or have a 'data' attribute
            items = subscription.get('items')
            if items:
                sub_items = items.get('data', []) if isinstance(items, dict) else items
                if sub_items and len(sub_items) > 0:
                    product = sub_items[0].get('price', {}).get('product', {})
                    if isinstance(product, dict):
                        update_data['active_plan_name'] = product.get('name')
                    else:
                        # If product is expanded, it should have a name attribute
                        update_data['active_plan_name'] = getattr(product, 'name', None)
        except Exception as e:
            print(f"WEBHOOK-API-ERROR: Could not retrieve subscription details for {stripe_subscription_id}. Error: {e}")

    if update_data:
        pocketbase_service.update_user(user_id, update_data)

    # --- Fulfill the Purchase ---
    try:
        line_items = stripe.checkout.Session.list_line_items(session.get('id'), limit=1, expand=['data.price.product'])
        if not line_items.data: return

        product_name, coins_to_add = _get_product_details_from_line_item(line_items.data[0])
        description = f"Purchase of {product_name}"
        transaction_type = "purchase" if session.get('mode') == 'payment' else "subscription"

        if coins_to_add > 0:
            pocketbase_service.add_coins(user_id, coins_to_add, description, session.get('payment_intent'), transaction_type)
            print(f"WEBHOOK-SUCCESS: Added {coins_to_add} coins to user {user_id} for {product_name}")
        else:
            print(f"WEBHOOK-WARN: Product in session {session.get('id')} has no 'coins' metadata.")
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


def handle_subscription_updated(subscription: dict):
    """
    Handles 'customer.subscription.updated' when a subscription is modified.
    This includes when cancel_at_period_end is set to True.
    """
    stripe_subscription_id = subscription.get('id')
    stripe_customer_id = subscription.get('customer')

    print(f"WEBHOOK-DEBUG: Processing subscription update for sub {stripe_subscription_id}, customer {stripe_customer_id}")
    print(f"WEBHOOK-DEBUG: cancel_at_period_end = {subscription.get('cancel_at_period_end')}")
    print(f"WEBHOOK-DEBUG: status = {subscription.get('status')}")

    user = pocketbase_service.get_user_by_stripe_customer_id(stripe_customer_id)

    if not user:
        print(f"WEBHOOK-WARN: No user found for Stripe customer {stripe_customer_id}")
        return

    print(f"WEBHOOK-DEBUG: Found user {user.id} with subscription_id {getattr(user, 'stripe_subscription_id', 'None')}")

    if user.stripe_subscription_id != stripe_subscription_id:
        print(f"WEBHOOK-WARN: User {user.id} subscription ID mismatch. Expected {stripe_subscription_id}, got {user.stripe_subscription_id}")
        return

    update_data = {}

    # Check if subscription is set to cancel at period end
    if subscription.get('cancel_at_period_end'):
        update_data['subscription_status'] = 'canceling'
        print(f"WEBHOOK-SUCCESS: Subscription {stripe_subscription_id} for user {user.id} is set to cancel at period end.")
    # Check if subscription was reactivated
    elif subscription.get('status') == 'active' and not subscription.get('cancel_at_period_end'):
        update_data['subscription_status'] = 'active'
        print(f"WEBHOOK-SUCCESS: Subscription {stripe_subscription_id} for user {user.id} was reactivated.")

    if update_data:
        success, message = pocketbase_service.update_user(user.id, update_data)
        if success:
            print(f"WEBHOOK-INFO: User {user.id} updated successfully with status: {update_data.get('subscription_status')}")
        else:
            print(f"WEBHOOK-ERROR: Failed to update user {user.id}: {message}")

def handle_customer_created(customer: dict):
    """
    Handles 'customer.created' event to link Stripe customer to user.
    This is useful when checkout.session.completed doesn't have the customer ID yet.
    """
    stripe_customer_id = customer.get('id')
    customer_email = customer.get('email')

    print(f"WEBHOOK-DEBUG: Customer created - ID: {stripe_customer_id}, Email: {customer_email}")

    if not customer_email:
        print(f"WEBHOOK-WARN: Customer {stripe_customer_id} has no email, cannot link to user")
        return

    # Find user by email
    try:
        users = pocketbase_service.admin_pb.collection("users").get_full_list(
            query_params={"filter": f'email="{customer_email}"'}
        )
        if users:
            user = users[0]
            # Only update if user doesn't already have a stripe_customer_id
            if not hasattr(user, 'stripe_customer_id') or not user.stripe_customer_id:
                pocketbase_service.update_user(user.id, {"stripe_customer_id": stripe_customer_id})
                print(f"WEBHOOK-SUCCESS: Linked Stripe customer {stripe_customer_id} to user {user.id}")
            else:
                print(f"WEBHOOK-INFO: User {user.id} already has stripe_customer_id: {user.stripe_customer_id}")
        else:
            print(f"WEBHOOK-WARN: No user found with email {customer_email}")
    except Exception as e:
        print(f"WEBHOOK-ERROR: Failed to link customer {stripe_customer_id}: {e}")


# --- Main Webhook Route ---

EVENT_HANDLERS = {
    'checkout.session.completed': handle_checkout_completed,
    'invoice.payment_succeeded': handle_invoice_succeeded,
    'customer.subscription.deleted': handle_subscription_deleted,
    'customer.subscription.updated': handle_subscription_updated,
    'customer.created': handle_customer_created,
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