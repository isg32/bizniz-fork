import stripe
from app.core.config import settings
from app.services import pocketbase_service

# Initialize the Stripe client globally
stripe.api_key = settings.STRIPE_API_KEY


def get_all_active_products_and_prices():
    """
    Fetches all active products from Stripe that are scoped to this specific application
    and separates them into one-time packs and recurring subscription plans.
    """
    # THIS IS THE UNIQUE IDENTIFIER FOR OUR APPLICATION
    APP_ID = "bizniz_ai_v1"

    try:
        # We now search for products with the correct app_id metadata
        products = stripe.Product.search(
            query=f"active:'true' AND metadata['app_id']:'{APP_ID}'",
            expand=['data.default_price']
        ).data

        one_time_packs = []
        subscription_plans = []

        for product in products:
            price = product.default_price
            if not price:
                continue

            item = {
                'price_id': price.id,
                'name': product.name,
                'description': product.description,
                'price': price.unit_amount / 100,
                'currency': price.currency.upper(),
                'coins': product.metadata.get('coins', 'N/A')
            }
            if price.type == 'recurring':
                subscription_plans.append(item)
            else:
                one_time_packs.append(item)
        
        one_time_packs.sort(key=lambda x: x['price'])
        subscription_plans.sort(key=lambda x: x['price'])
        
        return subscription_plans, one_time_packs
        
    except Exception as e:
        print(f"Stripe API error fetching products: {e}")
        return [], []


# The rest of the file (create_checkout_session, create_customer_portal_session)
# does not need to be changed.

def create_checkout_session(price_id: str, user_id: str, request: object, mode: str):
    """
    Creates a Stripe Checkout session for a given price ID, user, and mode.
    """
    try:
        base_url = str(request.base_url)
        user = pocketbase_service.get_user_by_id(user_id)
        
        session_params = {
            'payment_method_types': ['card'],
            'line_items': [{'price': price_id, 'quantity': 1}],
            'mode': mode,
            'success_url': f"{base_url}dashboard?payment=success",
            'cancel_url': f"{base_url}pricing?payment=cancelled",
            'client_reference_id': user_id,
        }
        
        if user and hasattr(user, 'stripe_customer_id') and user.stripe_customer_id:
            session_params['customer'] = user.stripe_customer_id
        elif user:
            session_params['customer_email'] = user.email

        checkout_session = stripe.checkout.Session.create(**session_params)
        return checkout_session
    except Exception as e:
        print(f"Stripe error creating checkout session for user {user_id}: {e}")
        return None


def create_customer_portal_session(stripe_customer_id: str, request: object):
    """
    Creates a Stripe Customer Portal session for a user to manage their subscription.
    """
    try:
        base_url = str(request.base_url)
        portal_session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=f"{base_url}dashboard",
        )
        return portal_session
    except Exception as e:
        print(f"Stripe error creating customer portal for {stripe_customer_id}: {e}")
        return None


def cancel_subscription(stripe_subscription_id: str) -> bool:
    """
    Cancels a Stripe subscription at the end of the billing period.
    Returns True if successful, False otherwise.
    """
    try:
        # Cancel at period end so user keeps access until billing period ends
        stripe.Subscription.modify(
            stripe_subscription_id,
            cancel_at_period_end=True
        )
        print(f"Successfully cancelled subscription {stripe_subscription_id} at period end.")
        return True
    except Exception as e:
        print(f"Stripe error cancelling subscription {stripe_subscription_id}: {e}")
        return False


def reactivate_subscription(stripe_subscription_id: str) -> bool:
    """
    Reactivates a Stripe subscription that was set to cancel at period end.
    Returns True if successful, False otherwise.
    """
    try:
        # Remove the cancel_at_period_end flag to reactivate
        stripe.Subscription.modify(
            stripe_subscription_id,
            cancel_at_period_end=False
        )
        print(f"Successfully reactivated subscription {stripe_subscription_id}.")
        return True
    except Exception as e:
        print(f"Stripe error reactivating subscription {stripe_subscription_id}: {e}")
        return False
