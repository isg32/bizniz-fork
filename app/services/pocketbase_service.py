import logging
from pocketbase import PocketBase
from pocketbase.utils import ClientResponseError
from app.core.config import settings

# --- Module-level clients ---
# These will be initialized once when the application starts up.
pb: PocketBase | None = None
admin_pb: PocketBase | None = None

# Set up a logger for this module
logger = logging.getLogger(__name__)

def init_clients():
    """
    Initializes the public and admin PocketBase clients.
    This is called once from the `startup_event` in main.py.
    """
    global pb, admin_pb
    try:
        if not settings.POCKETBASE_URL:
            raise ValueError("POCKETBASE_URL is not set in the environment.")
        
        # Public client for user-facing actions (register, login, etc.)
        pb = PocketBase(settings.POCKETBASE_URL)

        # Admin client for secure, backend-only actions (updating coins, etc.)
        admin_pb = PocketBase(settings.POCKETBASE_URL)
        admin_pb.admins.auth_with_password(
            settings.POCKETBASE_ADMIN_EMAIL,
            settings.POCKETBASE_ADMIN_PASSWORD
        )
        logger.info("Successfully authenticated PocketBase Admin client.")
        
    except Exception as e:
        logger.critical(f"FATAL: Could not initialize PocketBase clients. Error: {e}")
        # In a real app, you might want to exit if the DB connection fails
        # raise SystemExit(f"Could not connect to PocketBase: {e}") from e


# --- User Creation and Authentication (Public Client) ---

def create_user(email: str, password: str, name: str):
    """Creates a new user, sets default coin balance, and requests email verification."""
    if not pb:
        return None, "PocketBase client not initialized."
    try:
        user_data = {
            "email": email,
            "password": password,
            "passwordConfirm": password,
            "name": name,
            "coins": float(settings.FREE_SIGNUP_COINS),
            "subscription_status": "inactive"
        }
        record = pb.collection("users").create(user_data)
        pb.collection("users").request_verification(email)
        return record, None
    except ClientResponseError as e:
        logger.warning(f"Failed to create user {email}. Error: {e}")
        return None, str(e.data.get('data', 'Unknown error'))


def auth_with_password(email: str, password: str):
    """Authenticates a user with email and password."""
    if not pb:
        return None
    try:
        return pb.collection("users").auth_with_password(email, password)
    except ClientResponseError:
        return None


# --- Secure Data Management (Admin Client) ---

def get_user_by_id(user_id: str):
    """Fetches a single, complete user record by their ID using admin rights."""
    if not admin_pb:
        return None
    try:
        return admin_pb.collection("users").get_one(user_id)
    except ClientResponseError:
        return None


def get_user_from_token(token: str):
    """Validates a user's auth token and returns their LATEST user record."""
    if not admin_pb: return None
    try:
        # Create a temporary client instance to validate and refresh the token
        temp_client = PocketBase(settings.POCKETBASE_URL)
        temp_client.auth_store.save(token, None)
        auth_data = temp_client.collection("users").auth_refresh()
        
        # Now, use the secure ADMIN client to fetch the most up-to-date record
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


def add_coins(user_id: str, amount: int):
    """Atomically adds coins to a user's account to prevent race conditions."""
    if not admin_pb: return False, "Admin client not initialized"
    if amount <= 0: return True, "No coins to add."
    try:
        # The "+=" operator tells PocketBase to perform the addition on the server side
        update_data = {"coins+": amount}
        admin_pb.collection("users").update(user_id, update_data)
        logger.info(f"SUCCESS [CoinUpdate]: Atomically added {amount} coins to user {user_id}")
        return True, "Coins added successfully"
    except ClientResponseError as e:
        logger.error(f"FAIL [CoinUpdate]: Error adding coins for user {user_id}: {e}")
        return False, str(e)


def burn_coins(user_id: str, amount: float):
    """Securely deducts coins from a user's account using an atomic operation."""
    if not admin_pb: return False, "Admin client not initialized"
    try:
        user = get_user_by_id(user_id)
        if not user: return False, "User not found."
        
        if not hasattr(user, 'coins') or user.coins < amount:
            return False, "Insufficient coins."

        # Use the atomic operator "-=" to prevent race conditions.
        admin_pb.collection("users").update(user_id, {"coins-": amount})
        logger.info(f"SUCCESS [CoinBurn]: Burned {amount} coins for user {user_id}.")
        return True, f"Successfully burned {amount} coins."
    except ClientResponseError as e:
        return False, f"An error occurred: {str(e)}"

# --- Password, Verification, and Other Auth Functions (Public Client) ---

def request_password_reset(email: str):
    """Initiates a password reset request for the given email."""
    if not pb: return False, "PocketBase client not initialized."
    try:
        pb.collection("users").request_password_reset(email)
        return True, None
    except ClientResponseError as e:
        return False, str(e)


def confirm_password_reset(token: str, password: str, password_confirm: str):
    """Completes a password reset using the token and new password."""
    if not pb: return False, "PocketBase client not initialized."
    try:
        pb.collection("users").confirm_password_reset(token, password, password_confirm)
        return True, None
    except ClientResponseError as e:
        return False, str(e)


def confirm_verification(token: str):
    """Confirms a user's email address using the verification token."""
    if not pb: return False, "PocketBase client not initialized."
    try:
        pb.collection("users").confirm_verification(token)
        return True, None
    except ClientResponseError as e:
        return False, str(e)
