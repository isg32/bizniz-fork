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
        logger.critical(f"FATAL: Could not initialize PocketBase clients. Error: {e}")

# --- Transaction Logging (NEW) ---

def _create_transaction_record(
    user_id: str,
    transaction_type: str,
    amount: float,
    description: str,
    stripe_charge_id: str | None = None,
    metadata: dict | None = None
):
    """Internal helper to create a record in the 'transactions' collection."""
    if not admin_pb: return
    try:
        data = {
            "user": user_id,
            "type": transaction_type,
            "amount": amount,
            "description": description,
            "stripe_charge_id": stripe_charge_id,
            "metadata": metadata or {}
        }
        admin_pb.collection("transactions").create(data)
        logger.info(f"TRANSACTION-LOG: User {user_id}, Type: {transaction_type}, Amount: {amount}")
    except ClientResponseError as e:
        logger.error(f"TRANSACTION-FAIL: Could not log transaction for user {user_id}. Error: {e}")

def get_user_transactions(user_id: str):
    """Fetches all transactions for a specific user, sorted by most recent."""
    if not admin_pb: return []
    try:
        records = admin_pb.collection("transactions").get_full_list(
            query_params={"filter": f'user.id="{user_id}"', "sort": "-created"}
        )
        return records
    except ClientResponseError as e:
        logger.error(f"Error fetching transactions for user {user_id}: {e}")
        return []

# --- User Creation and Authentication (Unchanged) ---
# ... create_user, auth_with_password functions are unchanged ...

def create_user(email: str, password: str, name: str):
    """Creates a new user, sets default coin balance, and requests email verification."""
    if not pb: return None, "PocketBase client not initialized."
    try:
        user_data = { "email": email, "password": password, "passwordConfirm": password, "name": name, "coins": float(settings.FREE_SIGNUP_COINS), "subscription_status": "inactive" }
        record = pb.collection("users").create(user_data)
        pb.collection("users").request_verification(email)
        # Log the initial bonus coins
        _create_transaction_record(record.id, "bonus", settings.FREE_SIGNUP_COINS, "Free signup coins")
        return record, None
    except ClientResponseError as e:
        logger.warning(f"Failed to create user {email}. Error: {e}")
        return None, str(e.data.get('data', 'Unknown error'))
        
def auth_with_password(email: str, password: str):
    """Authenticates a user with email and password."""
    if not pb: return None
    try:
        return pb.collection("users").auth_with_password(email, password)
    except ClientResponseError:
        return None

# --- Secure Data Management (Updated) ---

def get_user_by_id(user_id: str):
    """Fetches a single, complete user record by their ID using admin rights."""
    if not admin_pb: return None
    try:
        return admin_pb.collection("users").get_one(user_id)
    except ClientResponseError:
        return None
        
def get_user_by_stripe_customer_id(customer_id: str):
    """Fetches a user record by their Stripe Customer ID."""
    if not admin_pb: return None
    try:
        records = admin_pb.collection("users").get_list(1, 1, {"filter": f'stripe_customer_id="{customer_id}"'})
        return records.items[0] if records.items else None
    except ClientResponseError as e:
        logger.error(f"Error fetching user by stripe_customer_id={customer_id}: {e}")
        return None

def get_user_from_token(token: str):
    """Validates a user's auth token and returns their LATEST user record."""
    if not admin_pb: return None
    try:
        temp_client = PocketBase(settings.POCKETBASE_URL)
        temp_client.auth_store.save(token, None)
        auth_data = temp_client.collection("users").auth_refresh()
        latest_user_record = admin_pb.collection("users").get_one(auth_data.record.id)
        return latest_user_record
    except ClientResponseError:
        return None

def update_user(user_id: str, data: dict):
    """Securely updates any field on a user's record using admin rights."""
    if not admin_pb: return False, "Admin client not initialized"
    try:
        admin_pb.collection("users").update(user_id, data)
        return True, "User updated successfully"
    except ClientResponseError as e:
        logger.error(f"Error updating user {user_id}: {e}")
        return False, str(e)

def add_coins(user_id: str, amount: int, description: str, stripe_charge_id: str | None = None, transaction_type: str = "purchase"):
    """Atomically adds coins to a user's account and logs the transaction."""
    if not admin_pb: return False, "Admin client not initialized"
    if amount <= 0: return True, "No coins to add."
    try:
        admin_pb.collection("users").update(user_id, {"coins+": amount})
        _create_transaction_record(user_id, transaction_type, amount, description, stripe_charge_id)
        return True, "Coins added successfully"
    except ClientResponseError as e:
        logger.error(f"FAIL [CoinUpdate]: Error adding coins for user {user_id}: {e}")
        return False, str(e)

def burn_coins(user_id: str, amount: float, description: str):
    """Securely deducts coins, logs the transaction."""
    if not admin_pb: return False, "Admin client not initialized"
    try:
        user = get_user_by_id(user_id)
        if not user: return False, "User not found."
        if not hasattr(user, 'coins') or user.coins < amount:
            return False, "Insufficient coins."
        admin_pb.collection("users").update(user_id, {"coins-": amount})
        _create_transaction_record(user_id, "spend", -amount, description)
        return True, f"Successfully burned {amount} coins."
    except ClientResponseError as e:
        return False, f"An error occurred: {str(e)}"

# --- Password, Verification Functions (Unchanged) ---
# ... request_password_reset, confirm_password_reset, confirm_verification are unchanged ...
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