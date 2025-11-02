"""
Test configuration and fixtures.
"""

# === CRITICAL: Mock config BEFORE any app imports ===
from unittest.mock import patch, MagicMock

# Apply the patch at module level so it's active during pytest collection
_test_config = {
    "SECRET_KEY": "test-secret-key",
    "POCKETBASE_URL": "http://test.pocketbase.io",
    "POCKETBASE_ADMIN_EMAIL": "admin@test.com",
    "POCKETBASE_ADMIN_PASSWORD": "test-password",
    "FRONTEND_URL": "http://localhost:5173",
    "STRIPE_API_KEY": "sk_test_123",
    "STRIPE_WEBHOOK_SECRET": "whsec_test_123",
    "GEMINI_API_KEY": "test-gemini-key",
    "ELEVENLABS_API_KEY": "test-elevenlabs-key",
    "RESEND_API_KEY": "re_test_123",
    "INTERNAL_API_SECRET_TOKEN": "internal-secret-token",
}

# Start the patch at import time
_config_patcher = patch("app.core.config.fetch_remote_config", return_value=_test_config)
_config_patcher.start()

# Now safe to import pytest and other modules
import pytest
from fastapi.testclient import TestClient


# === FIXTURES ===

@pytest.fixture(scope="function")
def client():
    """
    Creates a FastAPI TestClient with mocked configuration.
    Function-scoped to ensure test isolation.
    """
    # Import app after config is mocked
    from app.main import app
    
    # Clear any existing dependency overrides
    app.dependency_overrides.clear()
    
    with TestClient(app) as test_client:
        yield test_client
    
    # Cleanup
    app.dependency_overrides.clear()


@pytest.fixture
def mock_pocketbase_service(mocker):
    """Mocks the pocketbase_service module."""
    return mocker.patch("app.services.internal.pocketbase_service")


@pytest.fixture
def mock_stripe_service(mocker):
    """Mocks the stripe_service module."""
    return mocker.patch("app.services.internal.stripe_service")


@pytest.fixture
def mock_email_service(mocker):
    """Mocks the email_service module."""
    return mocker.patch("app.services.internal.email_service")


@pytest.fixture
def mock_user_data():
    """Standard test user data."""
    return {
        "id": "user123",
        "email": "test@example.com",
        "name": "Test User",
        "verified": True,
        "coins": 50.0,
        "subscription_status": "active",
        "active_plan_name": "Pro Plan",
        "stripe_customer_id": "cus_123",
        "stripe_subscription_id": "sub_123",
        "avatar": None,
        "collectionId": "users_collection",
    }


@pytest.fixture
def mock_pocketbase_auth_record(mock_user_data):
    """Mocks a PocketBase Record object with attributes."""
    record = MagicMock()
    record.id = mock_user_data["id"]
    record.email = mock_user_data["email"]
    record.name = mock_user_data["name"]
    record.verified = mock_user_data["verified"]
    return record


@pytest.fixture
def mock_pocketbase_auth_data(mock_pocketbase_auth_record):
    """Mocks the AuthData object returned by PocketBase authentication."""
    auth_data = MagicMock()
    auth_data.token = "fake-jwt-token"
    auth_data.record = mock_pocketbase_auth_record
    return auth_data


@pytest.fixture
def app_with_mock_user(client, mock_user_data):
    """
    Client with get_current_api_user dependency overridden.
    Use this when you need an authenticated user context.
    """
    from app.main import app
    from app.core.dependencies import get_current_api_user
    from app.schemas.user import User as UserSchema
    
    def override():
        return UserSchema.model_validate(mock_user_data)
    
    app.dependency_overrides[get_current_api_user] = override
    
    yield client
    
    app.dependency_overrides.clear()


# Cleanup the patcher when pytest exits
def pytest_sessionfinish(session, exitstatus):
    """Stop the config patcher when pytest session ends."""
    _config_patcher.stop()
