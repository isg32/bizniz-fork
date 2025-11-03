import requests
import uuid

# --- Configuration ---
# Make sure your FastAPI server is running at this address.
BASE_URL = "http://127.0.0.1:5000/api/v1"

# Generate a unique email for each test run to avoid "user already exists" errors
TEST_EMAIL = f"testuser_{uuid.uuid4().hex[:8]}@example.com"
TEST_PASSWORD = "a_very_strong_password_123"
TEST_NAME = "Test User"


def run_auth_tests():
    """Executes the full authentication test flow."""
    print("--- 🚀 Starting Authentication Flow Test ---")
    print(f"Using email: {TEST_EMAIL}")

    # 1. Register a new user
    print("\n[Step 1/5] Testing User Registration...")
    reg_payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "name": TEST_NAME,
    }
    try:
        response = requests.post(f"{BASE_URL}/auth/register", json=reg_payload)
        if response.status_code == 201:
            print("✅ SUCCESS: Registration successful (201 Created).")
            print("   > Response:", response.json())
        else:
            print(
                f"❌ FAILURE: Registration failed with status {response.status_code}."
            )
            print("   > Response:", response.text)
            return  # Stop the test if registration fails
    except requests.exceptions.ConnectionError as e:
        print(f"❌ FATAL: Could not connect to the server at {BASE_URL}.")
        print("   > Please make sure your FastAPI application is running.")
        return

    # 2. Attempt to log in (should fail as user is not verified)
    print("\n[Step 2/5] Testing Login (expecting failure for unverified user)...")
    login_payload = {"username": TEST_EMAIL, "password": TEST_PASSWORD}
    response = requests.post(f"{BASE_URL}/auth/token", data=login_payload)
    if response.status_code == 403:
        print("✅ SUCCESS: Login correctly failed for unverified user (403 Forbidden).")
        print("   > Detail:", response.json().get("detail"))
    else:
        print(f"❌ FAILURE: Expected 403 Forbidden, but got {response.status_code}.")
        print("   > Response:", response.text)

    # 3. Manual verification step
    print("\n" + "=" * 50)
    print("---> 🔴 MANUAL ACTION REQUIRED 🔴 <---")
    print(f"Please go to your PocketBase Admin UI (e.g., http://127.0.0.1:8090/_/)")
    print(
        f"Find the user '{TEST_EMAIL}' in the 'users' collection and manually verify their email."
    )
    input("---> Press Enter to continue after you have verified the user...")
    print("=" * 50 + "\n")

    # 4. Attempt to log in again (should now succeed)
    print("[Step 4/5] Testing Login (expecting success for verified user)...")
    access_token = None
    response = requests.post(f"{BASE_URL}/auth/token", data=login_payload)
    if response.status_code == 200:
        token_data = response.json()
        access_token = token_data.get("access_token")
        print("✅ SUCCESS: Login successful (200 OK).")
        print(f"   > Received Access Token: {access_token[:30]}...")
    else:
        print(f"❌ FAILURE: Login failed with status {response.status_code}.")
        print("   > Response:", response.text)
        return

    # 5. Test "Forgot Password" functionality
    print("\n[Step 5/5] Testing 'Forgot Password' request...")
    forgot_payload = {"email": TEST_EMAIL}
    response = requests.post(f"{BASE_URL}/auth/password/forgot", json=forgot_payload)
    if response.status_code == 202:
        print("✅ SUCCESS: 'Forgot Password' request was accepted (202 Accepted).")
        print("   > Response:", response.json())
    else:
        print(
            f"❌ FAILURE: 'Forgot Password' request failed with status {response.status_code}."
        )
        print("   > Response:", response.text)

    print("\n--- ✅ Authentication Flow Test Finished ---")
    if access_token:
        print("\nCOPY THIS TOKEN for the payments test script:")
        print("-" * 20)
        print(access_token)
        print("-" * 20)


if __name__ == "__main__":
    run_auth_tests()
