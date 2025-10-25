# app/services/internal/pocketbase_service.py

import logging
from pocketbase import PocketBase
from pocketbase.utils import ClientResponseError
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

# --- Transaction Logging (unchanged, omitted for brevity) ---
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

# --- User Creation and Authentication (unchanged, omitted for brevity) ---
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
    """Securely updates any field on a user's record using admin rights."""
    if not admin_pb: return False, "Admin client not initialized"
    try:
        # --- FINAL FIX ---
        # The bug is that the pocketbase-python SDK's update method NEVER takes a `files`
        # keyword argument. It also does not take `body` or `body_params`.
        # It ONLY accepts the data dictionary as the second positional argument.
        # The library is smart enough to detect if a file tuple is present in that dictionary
        # and will automatically create a multipart request.
        # This single line of code correctly handles ALL cases: simple data updates,
        # coin updates, and file uploads.

        updated_record = admin_pb.collection("users").update(user_id, data)
        
        # --- END OF FIX ---
        
        logger.info(f"User record {user_id} updated successfully.")
        return True, _enrich_user_record(updated_record)
    except ClientResponseError as e:
        logger.error(f"Error updating user {user_id}. Details: {e.data}")
        return False, str(e.data.get('data', 'Update failed'))

# --- Coin and Other Functions (unchanged, omitted for brevity) ---
def add_coins(user_id: str, amount: int, description: str, stripe_charge_id: str | None = None, transaction_type: str = "purchase"):
    if not admin_pb: return False, "Admin client not initialized"
    if amount <= 0: return True, "No coins to add."
    try:
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

def auth_with_oauth2(provider: str, code: str, code_verifier: str, redirect_url: str):
    if not pb: return None
    try:
        auth_data = pb.collection("users").auth_with_oauth2(
            provider=provider, code=code, code_verifier=code_verifier, redirect_url=redirect_url
        )
        user_id = auth_data.record.id
        user = get_user_by_id(user_id)
        if user and (not hasattr(user, 'coins') or user.coins == 0):
            add_coins(user_id, settings.FREE_SIGNUP_COINS, "Free signup coins via OAuth", transaction_type="bonus")
            logger.info(f"New OAuth user {user_id} received signup bonus")
        auth_data.record = user
        return auth_data
    except ClientResponseError as e:
        logger.error(f"OAuth2 authentication failed: {e}")
        return None
