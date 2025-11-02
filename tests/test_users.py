# tests/test_users.py

from unittest.mock import MagicMock

# --- Fixture for Authenticated Headers ---
import pytest


@pytest.fixture
def auth_headers():
    """Returns a dictionary with a dummy Authorization header."""
    return {"Authorization": "Bearer fake-token"}


# --- Helper Function to Mock the User Dependency ---
def mock_get_current_user(app, mock_user_data):
    """
    Overrides the `get_current_api_user` dependency to return a mock user
    without needing a real token.
    """
    from app.core.dependencies import get_current_api_user
    from app.schemas.user import User as UserSchema

    def override():
        return UserSchema.model_validate(mock_user_data)

    app.dependency_overrides[get_current_api_user] = override


# --- Tests for /users/me Endpoints ---


def test_get_current_user_me(
    client, auth_headers, mock_pocketbase_service, mock_user_data
):
    """
    Test successfully retrieving the current user's profile.

    Note: We mock `get_user_from_token` which is called by the dependency.
    """
    # Arrange: The `get_current_api_user` dependency will call this service function.
    # We configure the mock to return a valid user record.
    mock_user_record = MagicMock()
    for key, value in mock_user_data.items():
        setattr(mock_user_record, key, value)
    mock_pocketbase_service.get_user_from_token.return_value = mock_user_record

    # Act: Make a GET request to the protected /me endpoint with auth headers.
    response = client.get("/api/v1/users/me", headers=auth_headers)

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == mock_user_data["email"]
    assert data["id"] == mock_user_data["id"]
    mock_pocketbase_service.get_user_from_token.assert_called_once_with("fake-token")


def test_get_current_user_me_unauthorized(client):
    """
    Test that accessing a protected endpoint without a token fails.
    """
    # Act: Make the request without the Authorization header.
    response = client.get("/api/v1/users/me")

    # Assert: The API should return a 401 Unauthorized status.
    assert response.status_code == 401
    assert (
        "Not authenticated" in response.json()["detail"]
    )  # This comes from OAuth2PasswordBearer


def test_update_user_me(client, auth_headers, mock_pocketbase_service, mock_user_data):
    """
    Test successfully updating the current user's name.
    """
    # Arrange: Override the dependency to ensure a consistent user object.
    from app.main import app

    mock_get_current_user(app, mock_user_data)

    # Configure the mock for the update_user call. It should return (True, updated_record).
    updated_record = MagicMock()
    mock_pocketbase_service.update_user.return_value = (True, updated_record)

    # Act
    response = client.patch(
        "/api/v1/users/me", headers=auth_headers, json={"name": "Updated Name"}
    )

    # Assert
    assert response.status_code == 200
    mock_pocketbase_service.update_user.assert_called_once_with(
        mock_user_data["id"], {"name": "Updated Name"}
    )

    # Clean up the dependency override
    app.dependency_overrides = {}


def test_get_user_transactions(
    client, auth_headers, mock_pocketbase_service, mock_user_data
):
    """
    Test retrieving the transaction history for the authenticated user.
    """
    # Arrange
    from app.main import app

    mock_get_current_user(app, mock_user_data)

    mock_transactions = [
        MagicMock(
            id="tx1",
            type="purchase",
            amount=100,
            description="Test",
            created="2023-01-01T12:00:00Z",
        )
    ]
    mock_pocketbase_service.get_user_transactions.return_value = mock_transactions

    # Act
    response = client.get("/api/v1/users/me/transactions", headers=auth_headers)

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "tx1"
    mock_pocketbase_service.get_user_transactions.assert_called_once_with(
        mock_user_data["id"]
    )

    # Cleanup
    app.dependency_overrides = {}


# --- Tests for Internal Endpoints (/me/burn) ---


def test_burn_user_coins_success(
    client, auth_headers, mock_pocketbase_service, mock_user_data
):
    """
    Test successfully burning coins with both user token and internal API key.
    """
    # Arrange
    from app.main import app

    mock_get_current_user(app, mock_user_data)

    # Simulate successful coin burn
    mock_pocketbase_service.burn_coins.return_value = (True, "Success")

    # Simulate re-fetching the user with an updated balance
    updated_user = MagicMock()
    updated_user.coins = 40.0
    mock_pocketbase_service.get_user_by_id.return_value = updated_user

    # Add the internal API key to the headers
    internal_headers = auth_headers.copy()
    internal_headers["X-Internal-API-Key"] = "internal-secret-token"

    # Act
    response = client.post(
        "/api/v1/users/me/burn",
        headers=internal_headers,
        json={"amount": 10, "description": "Used AI feature"},
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["msg"] == "Coins burned successfully."
    assert data["coins_burned"] == 10
    assert data["new_coin_balance"] == 40.0
    mock_pocketbase_service.burn_coins.assert_called_once_with(
        user_id=mock_user_data["id"], amount=10, description="Used AI feature"
    )

    # Cleanup
    app.dependency_overrides = {}


def test_burn_user_coins_missing_internal_key(client, auth_headers, mock_user_data):
    """
    Test that the /burn endpoint fails without the internal API key.
    """
    # Arrange
    from app.main import app

    mock_get_current_user(app, mock_user_data)

    # Act: Make the request with only the user auth header.
    response = client.post(
        "/api/v1/users/me/burn",
        headers=auth_headers,
        json={"amount": 10, "description": "Used AI feature"},
    )

    # Assert: The API should return 401 Unauthorized because the internal key is missing.
    assert response.status_code == 401
    assert "Invalid or missing Internal API Key" in response.json()["detail"]

    # Cleanup
    app.dependency_overrides = {}


def test_burn_user_coins_insufficient_funds(
    client, auth_headers, mock_pocketbase_service, mock_user_data
):
    """
    Test the /burn endpoint when the user does not have enough coins.
    """
    # Arrange
    from app.main import app

    mock_get_current_user(app, mock_user_data)

    # Simulate the service returning an "Insufficient coins" error
    mock_pocketbase_service.burn_coins.return_value = (False, "Insufficient coins")

    internal_headers = auth_headers.copy()
    internal_headers["X-Internal-API-Key"] = "internal-secret-token"

    # Act
    response = client.post(
        "/api/v1/users/me/burn",
        headers=internal_headers,
        json={
            "amount": 100,
            "description": "Too expensive feature",
        },  # Try to burn more than they have
    )

    # Assert: The API should return a 402 Payment Required status.
    assert response.status_code == 402
    assert "Insufficient coins" in response.json()["detail"]

    # Cleanup
    app.dependency_overrides = {}
