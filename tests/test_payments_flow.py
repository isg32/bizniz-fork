import requests

# --- Configuration ---
BASE_URL = "http://127.0.0.1:5000/api/v1"

# 🔴 PASTE THE JWT TOKEN YOU GOT FROM THE AUTH TEST SCRIPT HERE 🔴
ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjb2xsZWN0aW9uSWQiOiJfcGJfdXNlcnNfYXV0aF8iLCJleHAiOjE3NjI3MjU2OTIsImlkIjoibmZ3a2pnanMybGNvNjR0IiwicmVmcmVzaGFibGUiOnRydWUsInR5cGUiOiJhdXRoIn0.h9uEnxw4WFa7e21NR0J86A2mBrNocyugCQUytMFeMm8"


def run_payments_tests():
    """Executes the payments API test flow."""
    print("--- 🚀 Starting Payments Flow Test ---")

    if "PASTE_YOUR_JWT_TOKEN_HERE" in ACCESS_TOKEN:
        print(
            "❌ FATAL: Please paste a valid JWT access token into the ACCESS_TOKEN variable in this script."
        )
        return

    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    price_id_to_purchase = None

    # 1. List all available products (this endpoint should be public)
    print("\n[Step 1/2] Testing Product Listing...")
    try:
        response = requests.get(f"{BASE_URL}/payments/products")
        if response.status_code == 200:
            print("✅ SUCCESS: Product listing endpoint is accessible (200 OK).")
            products_data = response.json()
            subs = products_data.get("subscription_plans", [])
            packs = products_data.get("one_time_packs", [])
            print(
                f"   > Found {len(subs)} subscription plans and {len(packs)} one-time packs."
            )

            # Grab a price_id to use for the next step
            if subs:
                price_id_to_purchase = subs[0]["price_id"]
                print(
                    f"   > Will use subscription price_id for next test: {price_id_to_purchase}"
                )
            else:
                print("   > WARNING: No subscription plans found to test checkout.")

        else:
            print(
                f"❌ FAILURE: Product listing failed with status {response.status_code}."
            )
            print("   > Response:", response.text)
            return
    except requests.exceptions.ConnectionError as e:
        print(f"❌ FATAL: Could not connect to the server at {BASE_URL}.")
        print("   > Please make sure your FastAPI application is running.")
        return

    # 2. Create a Stripe Checkout Session (requires authentication)
    if not price_id_to_purchase:
        print("\nSkipping Checkout Session test because no price_id was found.")
        print("\n--- ✅ Payments Flow Test Finished (partially) ---")
        return

    print("\n[Step 2/2] Testing Stripe Checkout Session Creation...")
    checkout_payload = {
        "price_id": price_id_to_purchase,
        "mode": "subscription",  # or "payment" for one-time packs
        "success_url": "https://example.com/success",
        "cancel_url": "https://example.com/cancel",
    }
    response = requests.post(
        f"{BASE_URL}/payments/checkout-session", headers=headers, json=checkout_payload
    )

    if response.status_code == 200:
        session_data = response.json()
        print("✅ SUCCESS: Stripe checkout session created successfully (200 OK).")
        print(f"   > Session ID: {session_data.get('session_id')}")
        print(f"   > Checkout URL: {session_data.get('url')}")
        print(
            "   > (You can manually open this URL in a browser to verify it leads to Stripe)"
        )
    elif response.status_code == 409:
        print(
            "✅ SUCCESS (as expected): Checkout correctly blocked because user already has a subscription (409 Conflict)."
        )
        print("   > Detail:", response.json().get("detail"))
    else:
        print(
            f"❌ FAILURE: Checkout session creation failed with status {response.status_code}."
        )
        print("   > Response:", response.text)

    print("\n--- ✅ Payments Flow Test Finished ---")


if __name__ == "__main__":
    run_payments_tests()
