import requests
import os

# --- Configuration ---
BASE_URL = "http://127.0.0.1:5000/api/v1"

# 🔴 PASTE THE JWT TOKEN YOU GOT FROM THE AUTH TEST SCRIPT HERE 🔴
ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjb2xsZWN0aW9uSWQiOiJfcGJfdXNlcnNfYXV0aF8iLCJleHAiOjE3NjI3MjU2OTIsImlkIjoibmZ3a2pnanMybGNvNjR0IiwicmVmcmVzaGFibGUiOnRydWUsInR5cGUiOiJhdXRoIn0.h9uEnxw4WFa7e21NR0J86A2mBrNocyugCQUytMFeMm8"

# The name of the avatar file located in the same directory as this script
AVATAR_FILENAME = "sample_avatar.png"


def run_user_profile_tests():
    """Executes the user profile API test flow."""
    print("--- 🚀 Starting User Profile Flow Test ---")

    if "PASTE_YOUR_JWT_TOKEN_HERE" in ACCESS_TOKEN:
        print("❌ FATAL: Please paste a valid JWT access token into the ACCESS_TOKEN variable in this script.")
        return

    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    original_name = None

    # 1. Get current user details
    print("\n[Step 1/4] Testing Get Current User ('/users/me')...")
    try:
        response = requests.get(f"{BASE_URL}/users/me", headers=headers)
        if response.status_code == 200:
            user_data = response.json()
            original_name = user_data.get("name")
            print("✅ SUCCESS: Fetched user data successfully (200 OK).")
            print(f"   > User ID: {user_data.get('id')}, Email: {user_data.get('email')}, Coins: {user_data.get('coins')}")
        else:
            print(f"❌ FAILURE: Failed to get user data. Status: {response.status_code}, Response: {response.text}")
            return
    except requests.exceptions.ConnectionError as e:
        print(f"❌ FATAL: Could not connect to the server at {BASE_URL}.")
        return

    # 2. Update user's name
    print("\n[Step 2/4] Testing Update User Name ('PATCH /users/me')...")
    new_name = f"Updated Name {os.urandom(3).hex()}"
    update_payload = {"name": new_name}
    response = requests.patch(f"{BASE_URL}/users/me", headers=headers, json=update_payload)
    if response.status_code == 200:
        updated_user = response.json()
        if updated_user.get("name") == new_name:
            print(f"✅ SUCCESS: User name updated to '{new_name}' (200 OK).")
        else:
            print(f"❌ FAILURE: API returned 200 OK, but name was not updated. Got: {updated_user.get('name')}")
    else:
        print(f"❌ FAILURE: Failed to update user name. Status: {response.status_code}, Response: {response.text}")

    # 3. Upload a user avatar
    print("\n[Step 3/4] Testing Avatar Upload ('POST /users/me/avatar')...")
    avatar_path = os.path.join(os.path.dirname(__file__), AVATAR_FILENAME)
    if not os.path.exists(avatar_path):
        print(f"❌ SKIPPING: Avatar file '{AVATAR_FILENAME}' not found in the 'tests/' directory.")
    else:
        with open(avatar_path, "rb") as f:
            files = {"avatar_file": (AVATAR_FILENAME, f, "image/png")}
            response = requests.post(f"{BASE_URL}/users/me/avatar", headers=headers, files=files)
            if response.status_code == 200:
                avatar_user = response.json()
                if avatar_user.get("avatar") and AVATAR_FILENAME in avatar_user.get("avatar"):
                    print("✅ SUCCESS: Avatar uploaded successfully (200 OK).")
                    print(f"   > New avatar URL contains filename: {avatar_user.get('avatar')}")
                else:
                    print("❌ FAILURE: API returned 200 OK, but avatar URL seems incorrect.")
            else:
                print(f"❌ FAILURE: Avatar upload failed. Status: {response.status_code}, Response: {response.text}")

    # 4. Get user transactions
    print("\n[Step 4/4] Testing Get User Transactions ('/users/me/transactions')...")
    response = requests.get(f"{BASE_URL}/users/me/transactions", headers=headers)
    if response.status_code == 200:
        transactions = response.json()
        print(f"✅ SUCCESS: Fetched user transactions successfully (200 OK). Found {len(transactions)} transaction(s).")
        if transactions:
            print(f"   > Most recent transaction: {transactions[0]}")
    else:
        print(f"❌ FAILURE: Failed to get transactions. Status: {response.status_code}, Response: {response.text}")

    print("\n--- ✅ User Profile Flow Test Finished ---")


if __name__ == "__main__":
    run_user_profile_tests()
