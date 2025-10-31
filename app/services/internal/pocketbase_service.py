# app/services/internal/pocketbase_service.py

import logging
from pocketbase import PocketBase
from pocketbase.utils import ClientResponseError
from pocketbase.client import FileUpload # ✅ THE CRITICAL IMPORT
from app.core.config import settings

# --- Module-level clients ---
pb: PocketBase | None = None
admin_pb: PocketBase | None = None
logger = logging.getLogger(__name__)

def init_clients():
    """Initializes the public and admin PocketBase clients."""
    global pb, admin_pb
    try:
        if not settings.POCKETBASE_URL:
            raise ValueError("POCKETBASE_URL is not set in the environment.")
        pb = PocketBase(settings.POCKETBASE_URL)
        admin_pb = PocketBase(settings.POCKETBASE_URL)
        admin_pb.admins.auth_with_password(
            settings.POCKETBASE_ADMIN_EMAIL,
            settings.POCKETBASE_ADMIN_PASSWORD
        )
        logger.info("Successfully authenticated PocketBase Admin client.")
    except Exception as e:
        logger.critical(f"FATAL: Could not initialize PocketBase clients. Error: {e}", exc_info=True)

# --- Helper Function ---
def _enrich_user_record(record):
    """Adds computed fields like the full avatar URL to a user record."""
    if record and hasattr(record, 'avatar') and record.avatar:
        record.avatar = f"{settings.POCKETBASE_URL}/api/files/{record.collection_id}/{record.id}/{record.avatar}"
    return record

# --- Transaction Logging ---
def _create_transaction_record(
    user_id: str,
    transaction_type: str,
    amount: float,
    description: str,
    stripe_charge_id: str | None = None,
    metadata: dict | None = None
):
    if not admin_pb: return
    try:
        data = {
            "user": user_id, "type": transaction_type, "amount": amount,
            "description": description, "stripe_charge_id": stripe_charge_id, "metadata": metadata or {}
        }
        admin_pb.collection("transactions").create(data)
        logger.info(f"TRANSACTION-LOG: User {user_id}, Type: {transaction_type}, Amount: {amount}")
    except ClientResponseError as e:
        logger.error(f"TRANSACTION-FAIL: Could not log transaction for user {user_id}. Details: {e.data}")

def get_user_transactions(user_id: str):
    if not admin_pb: return []
    try:
        return admin_pb.collection("transactions").get_full_list(
            query_params={"filter": f'user.id="{user_id}"', "sort": "-created"}
        )
    except ClientResponseError as e:
        logger.error(f"Error fetching transactions for user {user_id}: {e.data}")
        return []

# --- User Creation and Authentication ---
def create_user(email: str, password: str, name: str):
    if not pb: return None, "PocketBase client not initialized."
    try:
        user_data = {
            "email": email, "password": password, "passwordConfirm": password, "name": name,
            "coins": float(settings.FREE_SIGNUP_COINS), "subscription_status": "inactive"
        }
        record = pb.collection("users").create(user_data)
        pb.collection("users").request_verification(email)
        _create_transaction_record(record.id, "bonus", settings.FREE_SIGNUP_COINS, "Free signup coins")
        return record, None
    except ClientResponseError as e:
        logger.warning(f"Failed to create user {email}. Details: {e.data}")
        return None, str(e.data.get('data', 'Unknown error'))

def auth_with_password(email: str, password: str):
    if not pb: return None
    try:
        auth_data = pb.collection("users").auth_with_password(email, password)
        auth_data.record = _enrich_user_record(auth_data.record)
        return auth_data
    except ClientResponseError:
        logger.warning(f"Failed login attempt for email: {email}")
        return None

# --- Secure Data Management ---
def get_user_by_id(user_id: str):
    if not admin_pb: return None
    try:
        record = admin_pb.collection("users").get_one(user_id)
        return _enrich_user_record(record)
    except ClientResponseError:
        return None

def get_user_by_stripe_customer_id(customer_id: str):
    if not admin_pb: return None
    try:
        records = admin_pb.collection("users").get_full_list(
            query_params={"filter": f'stripe_customer_id = "{customer_id}"'}
        )
        return _enrich_user_record(records[0]) if records else None
    except ClientResponseError as e:
        logger.error(f"Error fetching user by stripe_customer_id={customer_id}: {e.data}")
        return None

def get_user_from_token(token: str):
    if not admin_pb: return None
    try:
        temp_client = PocketBase(settings.POCKETBASE_URL)
        temp_client.auth_store.save(token, None)
        auth_data = temp_client.collection("users").auth_refresh()
        latest_user_record = admin_pb.collection("users").get_one(auth_data.record.id)
        return _enrich_user_record(latest_user_record)
    except ClientResponseError:
        logger.warning("An invalid or expired token was presented for authentication.")
        return None

def update_user(user_id: str, data: dict):
    """
    Securely updates any field on a user's record using admin rights.
    This version uses the correct `FileUpload` class for file uploads.
    """
    if not admin_pb: return False, "Admin client not initialized"
    try:
        # --- ✅ THE `FileUpload` FIX ---
        # Create a copy to work with.
        data_to_send = data.copy()

        # Check if the 'avatar' key exists and its value is a tuple (our file data).
        if "avatar" in data_to_send and isinstance(data_to_send["avatar"], tuple):
            # If so, wrap the tuple in the special FileUpload class.
            data_to_send["avatar"] = FileUpload(data_to_send["avatar"])

        # The rest of the call is simple. The library handles the multipart logic.
        updated_record = admin_pb.collection("users").update(user_id, data_to_send)
        # --- END OF FIX ---

        logger.info(f"User record {user_id} updated successfully.")
        return True, _enrich_user_record(updated_record)

    except ClientResponseError as e:
        error_details = e.data if e.data else str(e)
        logger.error(f"Error updating user {user_id}. Details: {error_details}")
        return False, str(error_details)
    except Exception as e:
        logger.error(f"A non-PocketBase error occurred while updating user {user_id}: {e}", exc_info=True)
        return False, str(e)


# --- Coin and Other Functions ---
def add_coins(user_id: str, amount: int, description: str, stripe_charge_id: str | None = None, transaction_type: str = "purchase"):
    if not admin_pb: return False, "Admin client not initialized"
    if amount <= 0: return True, "No coins to add."
    try:
        # NOTE: Simple updates like this do NOT need the FileUpload class and work fine.
        admin_pb.collection("users").update(user_id, {"coins+": amount})
        _create_transaction_record(user_id, transaction_type, amount, description, stripe_charge_id)
        return True, "Coins added successfully"
    except ClientResponseError as e:
        logger.error(f"FAIL [CoinAddition]: Error adding coins for user {user_id}: {e.data}")
        return False, str(e)

def burn_coins(user_id: str, amount: float, description: str):
    if not admin_pb: return False, "Admin client not initialized"
    try:
        user = get_user_by_id(user_id)
        if not user:
            logger.warning(f"Attempted to burn coins for non-existent user ID: {user_id}")
            return False, "User not found."
        if not hasattr(user, 'coins') or user.coins < amount:
            logger.warning(f"Insufficient funds for user {user_id}. Has: {user.coins}, needs: {amount}")
            return False, "Insufficient coins."
        admin_pb.collection("users").update(user_id, {"coins-": amount})
        _create_transaction_record(user_id, "spend", -amount, description)
        return True, f"Successfully burned {amount} coins."
    except ClientResponseError as e:
        logger.error(f"FAIL [CoinBurn]: Error burning coins for user {user_id}: {e.data}")
        return False, f"An error occurred: {str(e)}"

# --- Password, Verification, OAuth2 Functions (Unchanged) ---
def request_password_reset(email: str):
    if not pb: return False, "PocketBase client not initialized."
    try:
        pb.collection("users").request_password_reset(email)
        return True, None
    except ClientResponseError as e:
        return False, str(e)

def confirm_password_reset(token: str, password: str, password_confirm: str):
    if not pb: return False, "PocketBase client not initialized."
    try:
        pb.collection("users").confirm_password_reset(token, password, password_confirm)
        return True, None
    except ClientResponseError as e:
        return False, str(e)

def confirm_verification(token: str):
    if not pb: return False, "PocketBase client not initialized."
    try:
        pb.collection("users").confirm_verification(token)
        return True, None
    except ClientResponseError as e:
        return False, str(e)

def get_oauth2_providers():
    if not pb: return []
    try:
        auth_methods = pb.collection("users").list_auth_methods()
        return auth_methods.auth_providers
    except Exception as e:
        logger.error(f"Error fetching OAuth2 providers: {e}")
        return []


# app/services/internal/pocketbase_service.py - OAuth Function Fix
def auth_with_oauth2(provider: str, code: str, code_verifier: str, redirect_url: str, pb_state: str = None):
    """
    Authenticates a user via OAuth2 and ensures proper user isolation.

    Args:
        provider: OAuth provider name (e.g., 'google', 'github')
        code: Authorization code from OAuth provider
        code_verifier: PKCE code verifier
        redirect_url: The redirect URL (must match what's registered)
        pb_state: PocketBase's original state (optional, for internal use)
    """
    if not pb:
        logger.error("PocketBase client not initialized for OAuth")
        return None

    try:
        # ✅ FIX 1: Create a NEW isolated PocketBase client for this OAuth attempt
        # This prevents token conflicts when multiple users authenticate simultaneously
        oauth_client = PocketBase(settings.POCKETBASE_URL)

        # ✅ FIX 2: Perform OAuth authentication with the isolated client
        # Note: We don't pass pb_state to PocketBase SDK - it's only for our tracking
        auth_data = oauth_client.collection("users").auth_with_oauth2(
            provider=provider,
            code=code,
            code_verifier=code_verifier,
            redirect_url=redirect_url
        )

        # ✅ FIX 3: Immediately extract the user ID BEFORE any other operations
        user_id = auth_data.record.id
        user_email = auth_data.record.email

        logger.info(f"OAuth2 authentication successful for user {user_id} ({user_email}) via {provider}")

        # ✅ FIX 4: Get the complete user record using admin client for accuracy
        user = get_user_by_id(user_id)

        if not user:
            logger.error(f"Critical: OAuth user {user_id} authenticated but record not found")
            return None

        # ✅ FIX 5: Check if this is a new user (no coins or zero coins)
        is_new_user = not hasattr(user, 'coins') or user.coins == 0

        if is_new_user:
            success, msg = add_coins(
                user_id,
                settings.FREE_SIGNUP_COINS,
                "Free signup coins via OAuth",
                transaction_type="bonus"
            )
            if success:
                logger.info(f"New OAuth user {user_id} received {settings.FREE_SIGNUP_COINS} signup bonus")
            else:
                logger.warning(f"Failed to add signup bonus for new OAuth user {user_id}: {msg}")

            # Refresh the user record after adding coins
            user = get_user_by_id(user_id)

        # ✅ FIX 6: Return the auth data with the verified user record
        auth_data.record = user

        return auth_data

    except ClientResponseError as e:
        logger.error(f"OAuth2 authentication failed for provider {provider}: {e.data}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during OAuth2 authentication: {e}", exc_info=True)
        return None
