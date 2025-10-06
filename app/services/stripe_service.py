import stripe
from app.core.config import settings
from app.services import pocketbase_service

# Initialize the Stripe client globally
stripe.api_key = settings.STRIPE_API_KEY


def get_all_active_products_and_prices():
    """
    Fetches all active products from Stripe and separates them into
    one-time packs and recurring subscription plans.
    """
    try:
        prices = stripe.Price.list(active=True, expand=['data.product']).data
        
        one_time_packs = []
        subscription_plans = []

        for price in prices:
            product = price.product
            if not (product and product.active):
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
        
        # Sort both lists by price
        one_time_packs.sort(key=lambda x: x['price'])
        subscription_plans.sort(key=lambda x: x['price'])
        
        return subscription_plans, one_time_packs
        
    except Exception as e:
        print(f"Stripe API error fetching products: {e}")
        return [], []


def create_checkout_session(price_id: str, user_id: str, request: object, mode: str):
    """
    Creates a Stripe Checkout session for a given price ID, user, and mode.
    Handles associating the checkout with an existing Stripe customer if one exists.
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
        
        # Best Practice: If user is already a customer, use their existing customer ID.
        if user and user.stripe_customer_id:
            session_params['customer'] = user.stripe_customer_id
        else:
            # If it's a new customer, pre-fill their email address
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