import stripe
from app.core.config import settings

# Initialize the Stripe client globally
stripe.api_key = settings.STRIPE_API_KEY

def get_all_active_products_and_prices():
    """
    Fetches all active products from Stripe that are one-time purchases.
    Returns a list of products with their price details.
    """
    try:
        # We list prices and expand the 'product' object for each price
        prices = stripe.Price.list(active=True, expand=['data.product'], type='one_time').data
        
        products_list = []
        for price in prices:
            product = price.product
            if product and product.active:
                products_list.append({
                    'price_id': price.id,
                    'name': product.name,
                    'description': product.description,
                    'price': price.unit_amount / 100, # Price in dollars
                    'currency': price.currency.upper(),
                    'coins': product.metadata.get('coins', 'N/A')
                })
        
        # Sort by price, lowest first
        products_list.sort(key=lambda x: x['price'])
        return products_list
        
    except Exception as e:
        print(f"Stripe API error fetching products: {e}")
        return []

def create_checkout_session(price_id: str, user_id: str, request: object):
    """
    Creates a Stripe Checkout session for a one-time purchase.
    """
    try:
        # Get the base URL from the request
        base_url = str(request.base_url)
        
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='payment',
            success_url=f"{base_url}dashboard?payment=success",
            cancel_url=f"{base_url}pricing?payment=cancelled",
            # This is how we link the Stripe payment back to our user
            client_reference_id=user_id
        )
        return checkout_session
    except Exception as e:
        print(f"Stripe error creating checkout session for user {user_id}: {e}")
        return None
