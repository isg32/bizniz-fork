import stripe
from fastapi import APIRouter, Request, Header, HTTPException
from app.core.config import settings
from app.services import pocketbase_service

router = APIRouter()

@router.post("/stripe-webhook", include_in_schema=False)
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    """
    Listens for events from Stripe.
    This is the endpoint that fulfills orders after a successful payment.
    """
    try:
        payload = await request.body()
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=stripe_signature,
            secret=settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid signature: {e}")

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        user_id = session.get('client_reference_id')
        if not user_id:
            print(f"WEBHOOK-ERROR: 'client_reference_id' missing in session {session.get('id')}.")
            return {"status": "error", "reason": "Missing user ID"}

        try:
            line_items = stripe.checkout.Session.list_line_items(session.id, limit=1, expand=['data.price.product'])
            if not line_items.data:
                print(f"WEBHOOK-ERROR: No line items found for session {session.get('id')}.")
                return {"status": "error", "reason": "No line items"}
                
            product = line_items.data[0].price.product
            coins_to_add = int(product.metadata.get('coins', 0))

            if coins_to_add > 0:
                success, message = pocketbase_service.add_coins(user_id, coins_to_add)
                if success:
                    print(f"WEBHOOK-SUCCESS: Added {coins_to_add} coins to user {user_id}.")
                else:
                    print(f"WEBHOOK-CRITICAL: FAILED to add coins to user {user_id}. Reason: {message}")
            else:
                 print(f"WEBHOOK-WARN: Product {product.id} has no 'coins' metadata.")

        except Exception as e:
            print(f"WEBHOOK-API-ERROR: Failed to process line items for session {session.get('id')}: {e}")
            return {"status": "error", "reason": "API error"}

    else:
        print(f"WEBHOOK-INFO: Unhandled event type {event['type']}")

    return {"status": "success"}