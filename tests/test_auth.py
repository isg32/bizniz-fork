# tests/test_auth.py

from unittest.mock import MagicMock

# --- Test User Registration ---


def test_register_user_success(client, mock_pocketbase_service):
    """
    Test successful user registration.
    """
    # Arrange: Configure the pocketbase_service mock to simulate a successful user creation.
    # The `create_user` function should return a (record, None) tuple on success.
    mock_user_record = MagicMock()
    mock_pocketbase_service.create_user.return_value = (mock_user_record, None)

    # Act: Make a POST request to the /register endpoint.
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "password123",
            "name": "New User",
        },
    )

    # Assert: Check that the API returns a 201 Created status and the correct data.
    assert response.status_code == 201
    # Check that our mock was called exactly once with the correct arguments.
    mock_pocketbase_service.create_user.assert_called_once_with(
        email="newuser@example.com", password="password123", name="New User"
    )


def test_register_user_already_exists(client, mock_pocketbase_service):
    """
    Test registration failure when a user with the same email already exists.
    """
    # Arrange: Configure the mock to simulate a "validation_not_unique" error.
    mock_pocketbase_service.create_user.return_value = (None, "validation_not_unique")

    # Act
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "existing@example.com",
            "password": "password123",
            "name": "Existing User",
        },
    )

    # Assert: Check that the API returns a 409 Conflict status code and the correct error detail.
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


# --- Test User Login (Token Endpoint) ---


def test_login_success(client, mock_pocketbase_service, mock_pocketbase_auth_data):
    """
    Test successful login for a verified user.
    """
    # Arrange: Configure the mock to return a valid AuthData object.
    mock_pocketbase_service.auth_with_password.return_value = mock_pocketbase_auth_data

    # Act: Make a POST request to the /token endpoint using form data.
    response = client.post(
        "/api/v1/auth/token",
        data={"username": "test@example.com", "password": "password123"},
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "fake-jwt-token"
    assert data["token_type"] == "bearer"
    mock_pocketbase_service.auth_with_password.assert_called_once_with(
        email="test@example.com", password="password123"
    )


def test_login_unverified_user(
    client, mock_pocketbase_service, mock_pocketbase_auth_data
):
    """
    Test login failure for an unverified user.
    """
    # Arrange: Simulate an unverified user by setting the 'verified' flag to False.
    mock_pocketbase_auth_data.record.verified = False
    mock_pocketbase_service.auth_with_password.return_value = mock_pocketbase_auth_data

    # Act
    response = client.post(
        "/api/v1/auth/token",
        data={"username": "unverified@example.com", "password": "password123"},
    )

    # Assert: The API should return a 403 Forbidden status.
    assert response.status_code == 403
    assert "Account not verified" in response.json()["detail"]


def test_login_incorrect_password(client, mock_pocketbase_service):
    """
    Test login failure with incorrect credentials.
    """
    # Arrange: Configure the mock to return None, simulating a failed login.
    mock_pocketbase_service.auth_with_password.return_value = None

    # Act
    response = client.post(
        "/api/v1/auth/token",
        data={"username": "test@example.com", "password": "wrongpassword"},
    )

    # Assert: The API should return a 401 Unauthorized status.
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]


# --- Test Password Reset Flow ---


def test_request_password_reset(client, mock_pocketbase_service):
    """
    Test the endpoint for requesting a password reset.
    """
    # Arrange
    mock_pocketbase_service.request_password_reset.return_value = (True, None)

    # Act
    response = client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "test@example.com"},
    )

    # Assert
    assert response.status_code == 202
    assert "password reset link has been sent" in response.json()["msg"]
    mock_pocketbase_service.request_password_reset.assert_called_once_with(
        "test@example.com"
    )


def test_confirm_password_reset_success(client, mock_pocketbase_service):
    """
    Test successfully setting a new password with a valid token.
    """
    # Arrange
    mock_pocketbase_service.confirm_password_reset.return_value = (True, None)

    # Act
    response = client.post(
        "/api/v1/auth/password/reset-confirm",
        json={
            "token": "valid-reset-token",
            "password": "newpassword123",
            "password_confirm": "newpassword123",
        },
    )

    # Assert
    assert response.status_code == 200
    assert "Password has been reset successfully" in response.json()["msg"]
    mock_pocketbase_service.confirm_password_reset.assert_called_once()


def test_confirm_password_reset_mismatch(client):
    """
    Test password reset failure when passwords do not match.
    """
    # Act
    response = client.post(
        "/api/v1/auth/password/reset-confirm",
        json={
            "token": "any-token",
            "password": "newpassword123",
            "password_confirm": "differentpassword",
        },
    )

    # Assert: The API should return a 422 Unprocessable Entity status.
    assert response.status_code == 422
    assert "Passwords do not match" in response.json()["detail"]


# --- Test OAuth Flow ---


def test_get_oauth2_providers(client, mock_pocketbase_service):
    """
    Test the endpoint that lists available OAuth2 providers.
    """
    # Arrange: Simulate the provider data returned by the service.
    mock_providers = [{"name": "google", "authUrl": "http://google.com/auth"}]
    mock_pocketbase_service.get_oauth2_providers.return_value = mock_providers

    # Act
    response = client.get("/api/v1/auth/oauth2/providers")

    # Assert
    assert response.status_code == 200
    assert response.json() == {"providers": mock_providers}


def test_oauth2_callback_success(
    client, mock_pocketbase_service, mock_pocketbase_auth_data
):
    """
    Test the final step of the OAuth2 flow where the code is exchanged for a token.
    """
    # Arrange
    mock_pocketbase_service.auth_with_oauth2.return_value = mock_pocketbase_auth_data

    # Act
    response = client.post(
        "/api/v1/auth/oauth2/google/callback",
        json={
            "code": "auth-code-from-google",
            "code_verifier": "pkce-code-verifier",
            "redirect_uri": "http://localhost:5173/callback",
        },
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "fake-jwt-token"
    mock_pocketbase_service.auth_with_oauth2.assert_called_once()
