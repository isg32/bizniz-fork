# app/services/internal/pocketbase_service.py

import logging
from pocketbase import PocketBase
from pocketbase.utils import ClientResponseError
from pocketbase.client import FileUpload
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
            raise ValueError("POCKETBASE_URL is not set.")
        pb = PocketBase(settings.POCKETBASE_URL)
        admin_pb = PocketBase(settings.POCKETBASE_URL)
        admin_pb.admins.auth_with_password(
            settings.POCKETBASE_ADMIN_EMAIL, settings.POCKETBASE_ADMIN_PASSWORD
        )
        logger.info("Successfully authenticated PocketBase Admin client.")
    except Exception as e:
        logger.critical(
            f"FATAL: Could not initialize PocketBase clients. Error: {e}", exc_info=True
        )
        raise e  # Re-raise to stop the application startup


# --- REMOVED ---
# The _enrich_user_record helper function has been removed.
# This logic is now handled automatically by the Pydantic User schema's @model_validator.


# --- Transaction Logging (Unchanged) ---
def _create_transaction_record(
    user_id: str,
    transaction_type: str,
    amount: float,
    description: str,
    stripe_charge_id: str | None = None,
    metadata: dict | None = None,
):
    if not admin_pb:
        return
    try:
        data = {
            "user": user_id,
            "type": transaction_type,
            "amount": amount,
            "description": description,
            "stripe_charge_id": stripe_charge_id,
            "metadata": metadata or {},
        }
        admin_pb.collection("transactions").create(data)
        logger.info(
            f"TRANSACTION-LOG: User {user_id}, Type: {transaction_type}, Amount: {amount}"
        )
    except ClientResponseError as e:
        logger.error(
            f"TRANSACTION-FAIL: Could not log transaction for user {user_id}. Details: {e.data}"
        )


def get_user_transactions(user_id: str):
    if not admin_pb:
        return []
    try:
        return admin_pb.collection("transactions").get_full_list(
            query_params={"filter": f'user.id="{user_id}"', "sort": "-created"}
        )
    except ClientResponseError as e:
        logger.error(f"Error fetching transactions for user {user_id}: {e.data}")
        return []


# --- User Management ---
def create_user(email: str, password: str, name: str):
    if not pb:
        return None, "PocketBase client not initialized."
    try:
        user_data = {
            "email": email,
            "password": password,
            "passwordConfirm": password,
            "name": name,
            "coins": float(settings.FREE_SIGNUP_COINS),
            "subscription_status": "inactive",
        }
        record = pb.collection("users").create(user_data)
        # Request verification after successful creation
        pb.collection("users").request_verification(email)
        _create_transaction_record(
            record.id, "bonus", settings.FREE_SIGNUP_COINS, "Free signup coins"
        )
        return record, None
    except ClientResponseError as e:
        logger.warning(f"Failed to create user {email}. Details: {e.data}")
        return None, str(e.data.get("data", "Unknown error"))


def auth_with_password(email: str, password: str):
    if not pb:
        return None
    try:
        # The returned auth_data.record is now passed directly to the User schema,
        # which will handle the avatar URL enrichment.
        return pb.collection("users").auth_with_password(email, password)
    except ClientResponseError:
        logger.warning(f"Failed login attempt for email: {email}")
        return None


def get_user_by_id(user_id: str):
    if not admin_pb:
        return None
    try:
        return admin_pb.collection("users").get_one(user_id)
    except ClientResponseError:
        return None


def get_user_by_email(email: str):
    """Utility function to find a user by their email address."""
    if not admin_pb:
        return None
    try:
        records = admin_pb.collection("users").get_full_list(
            query_params={"filter": f'email = "{email}"'}
        )
        return records[0] if records else None
    except ClientResponseError as e:
        logger.error(f"Error fetching user by email={email}: {e.data}")
        return None


def get_user_by_stripe_customer_id(customer_id: str):
    if not admin_pb:
        return None
    try:
        records = admin_pb.collection("users").get_full_list(
            query_params={"filter": f'stripe_customer_id = "{customer_id}"'}
        )
        return records[0] if records else None
    except ClientResponseError as e:
        logger.error(
            f"Error fetching user by stripe_customer_id={customer_id}: {e.data}"
        )
        return None


def get_user_by_stripe_subscription_id(subscription_id: str):
    """Finds a user by their active Stripe subscription ID."""
    if not admin_pb:
        return None
    try:
        records = admin_pb.collection("users").get_full_list(
            query_params={"filter": f'stripe_subscription_id = "{subscription_id}"'}
        )
        return records[0] if records else None
    except ClientResponseError as e:
        logger.error(
            f"Error fetching user by stripe_subscription_id={subscription_id}: {e.data}"
        )
        return None


def get_user_from_token(token: str):
    if not pb:
        return None
    try:
        # Auth with a temporary client to not pollute the global one
        temp_client = PocketBase(settings.POCKETBASE_URL)
        temp_client.auth_store.save(token, None)
        # Refresh to validate the token against the server
        auth_data = temp_client.collection("users").auth_refresh()
        # Fetch the latest, complete user record with admin rights
        return get_user_by_id(auth_data.record.id)
    except ClientResponseError:
        logger.warning("An invalid or expired token was presented for authentication.")
        return None


def update_user(user_id: str, data: dict):
    if not admin_pb:
        return False, "Admin client not initialized"
    try:
        data_to_send = data.copy()
        if "avatar" in data_to_send and isinstance(data_to_send["avatar"], tuple):
            data_to_send["avatar"] = FileUpload(data_to_send["avatar"])

        updated_record = admin_pb.collection("users").update(user_id, data_to_send)
        logger.info(f"User record {user_id} updated successfully.")
        return True, updated_record
    except ClientResponseError as e:
        error_details = e.data if e.data else str(e)
        logger.error(f"Error updating user {user_id}. Details: {error_details}")
        return False, str(error_details)
    except Exception as e:
        logger.error(
            f"A non-PocketBase error occurred while updating user {user_id}: {e}",
            exc_info=True,
        )
        return False, str(e)


# --- Coin Management (Unchanged logic) ---
def add_coins(
    user_id: str,
    amount: int,
    description: str,
    stripe_charge_id: str | None = None,
    transaction_type: str = "purchase",
):
    if not admin_pb:
        return False, "Admin client not initialized"
    if amount <= 0:
        return True, "No coins to add."
    try:
        admin_pb.collection("users").update(user_id, {"coins+": amount})
        _create_transaction_record(
            user_id, transaction_type, amount, description, stripe_charge_id
        )
        return True, "Coins added successfully"
    except ClientResponseError as e:
        logger.error(
            f"FAIL [CoinAddition]: Error adding coins for user {user_id}: {e.data}"
        )
        return False, str(e)


def burn_coins(user_id: str, amount: float, description: str):
    if not admin_pb:
        return False, "Admin client not initialized"
    try:
        user = get_user_by_id(user_id)
        if not user or not hasattr(user, "coins") or user.coins < amount:
            return False, "Insufficient coins."
        admin_pb.collection("users").update(user_id, {"coins-": amount})
        _create_transaction_record(user_id, "spend", -amount, description)
        return True, f"Successfully burned {amount} coins."
    except ClientResponseError as e:
        logger.error(
            f"FAIL [CoinBurn]: Error burning coins for user {user_id}: {e.data}"
        )
        return False, f"An error occurred: {str(e)}"


# --- Verification and Password Reset (Unchanged logic) ---
def request_password_reset(email: str):
    if not pb:
        return False, "PocketBase client not initialized."
    try:
        pb.collection("users").request_password_reset(email)
        return True, None
    except ClientResponseError as e:
        return False, str(e)


def confirm_password_reset(token: str, password: str, password_confirm: str):
    if not pb:
        return False, "PocketBase client not initialized."
    try:
        pb.collection("users").confirm_password_reset(token, password, password_confirm)
        return True, None
    except ClientResponseError as e:
        return False, str(e)


def confirm_verification(token: str):
    if not pb:
        return False, "PocketBase client not initialized."
    try:
        pb.collection("users").confirm_verification(token)
        return True, None
    except ClientResponseError as e:
        return False, str(e)


# --- OAuth2 Flow ---
def get_oauth2_providers():
    if not pb:
        return []
    try:
        auth_methods = pb.collection("users").list_auth_methods()
        return auth_methods.auth_providers
    except Exception as e:
        logger.error(f"Error fetching OAuth2 providers: {e}")
        return []


def auth_with_oauth2(provider: str, code: str, code_verifier: str, redirect_url: str):
    if not pb:
        return None
    try:
        # Use a new, isolated client for each OAuth attempt to prevent race conditions
        oauth_client = PocketBase(settings.POCKETBASE_URL)
        auth_data = oauth_client.collection("users").auth_with_oauth2(
            provider=provider,
            code=code,
            code_verifier=code_verifier,
            redirect_url=redirect_url,
        )

        user_id = auth_data.record.id
        user = get_user_by_id(user_id)
        if not user:
            logger.error(
                f"Critical: OAuth user {user_id} authenticated but record not found"
            )
            return None

        # Check if this is a brand new user (coins will be 0)
        if user.coins == 0:
            add_coins(
                user_id,
                settings.FREE_SIGNUP_COINS,
                "Free signup coins via OAuth",
                transaction_type="bonus",
            )

        # Return the auth data, the calling function will validate it into a User schema
        return auth_data
    except ClientResponseError as e:
        logger.error(f"OAuth2 authentication failed for provider {provider}: {e.data}")
        return None
