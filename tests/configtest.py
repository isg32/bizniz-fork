# tests/conftest.py

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock


# --- 1. Mock Settings BEFORE app is imported ---
@pytest.fixture(scope="session", autouse=True)
def mock_settings(session_mocker):
    """
    This autouse fixture runs once before any tests. It patches the remote
    config fetch to ensure a consistent test configuration is used and
    prevents real network calls during test discovery.
    """
    test_config = {
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
    session_mocker.patch(
        "app.core.config.fetch_remote_config", return_value=test_config
    )


# --- 2. Import the App and Create Test Client ---
@pytest.fixture(scope="session")
def client():
    """
    Creates a FastAPI TestClient. The `app` is imported here to ensure
    that `mock_settings` has already run and patched the configuration.
    """
    # This deferred import is the key to fixing the problem.
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


# --- 3. Mocks for External Services ---
@pytest.fixture
def mock_pocketbase_service(mocker):
    """Mocks all functions in the pocketbase_service module."""
    return mocker.patch("app.services.internal.pocketbase_service")


@pytest.fixture
def mock_stripe_service(mocker):
    """Mocks all functions in the stripe_service module."""
    return mocker.patch("app.services.internal.stripe_service")


@pytest.fixture
def mock_email_service(mocker):
    """Mocks all functions in the email_service module."""
    return mocker.patch("app.services.internal.email_service")


# --- 4. Reusable Mock Data Fixtures ---
@pytest.fixture
def mock_user_data():
    """A dictionary representing a standard user."""
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
    """Mocks a PocketBase Record object, which has attributes, not dict keys."""
    record = MagicMock()
    record.id = mock_user_data["id"]
    record.email = mock_user_data["email"]
    record.name = mock_user_data["name"]
    record.verified = mock_user_data["verified"]
    return record


@pytest.fixture
def mock_pocketbase_auth_data(mock_pocketbase_auth_record):
    """Mocks the complete AuthData object returned by PocketBase on login."""
    auth_data = MagicMock()
    auth_data.token = "fake-jwt-token"
    auth_data.record = mock_pocketbase_auth_record
    return auth_data
