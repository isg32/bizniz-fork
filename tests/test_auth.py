# tests/test_auth.py

# --- Test User Registration ---

def test_register_user_success(client, mock_pocketbase_service, mock_user_data):
    """
    Test successful user registration.
    """
    # ARRANGE: Return a dictionary, not a MagicMock. Pydantic can validate this.
    mock_pocketbase_service.create_user.return_value = (mock_user_data, None)

    # ACT
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "password123",
            "name": "New User",
        },
    )

    # ASSERT
    assert response.status_code == 201
    assert response.json()["email"] == mock_user_data["email"]
    mock_pocketbase_service.create_user.assert_called_once_with(
        email="newuser@example.com", password="password123", name="New User"
    )


def test_register_user_already_exists(client, mock_pocketbase_service):
    """
    Test registration failure when a user with the same email already exists.
    """
    # ARRANGE
    mock_pocketbase_service.create_user.return_value = (None, "validation_not_unique")

    # ACT
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "existing@example.com",
            "password": "password123",
            "name": "Existing User",
        },
    )

    # ASSERT
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


# --- Test User Login (Token Endpoint) ---

def test_login_success(client, mock_pocketbase_service, mock_pocketbase_auth_data):
    """
    Test successful login for a verified user.
    """
    # ARRANGE
    mock_pocketbase_service.auth_with_password.return_value = mock_pocketbase_auth_data

    # ACT
    response = client.post(
        "/api/v1/auth/token",
        data={"username": "test@example.com", "password": "password123"},
    )

    # ASSERT
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
    # ARRANGE
    mock_pocketbase_auth_data.record.verified = False
    mock_pocketbase_service.auth_with_password.return_value = mock_pocketbase_auth_data

    # ACT
    response = client.post(
        "/api/v1/auth/token",
        data={"username": "unverified@example.com", "password": "password123"},
    )

    # ASSERT
    assert response.status_code == 403
    assert "Account not verified" in response.json()["detail"]


def test_login_incorrect_password(client, mock_pocketbase_service):
    """
    Test login failure with incorrect credentials.
    """
    # ARRANGE
    mock_pocketbase_service.auth_with_password.return_value = None

    # ACT
    response = client.post(
        "/api/v1/auth/token",
        data={"username": "test@example.com", "password": "wrongpassword"},
    )

    # ASSERT
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]


# --- Test Password Reset Flow ---

def test_request_password_reset(client, mock_pocketbase_service):
    """
    Test the endpoint for requesting a password reset.
    """
    # ARRANGE
    # This mock was correct, the issue was elsewhere.
    mock_pocketbase_service.request_password_reset.return_value = (True, None)

    # ACT
    response = client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "test@example.com"},
    )

    # ASSERT
    assert response.status_code == 202
    assert "password reset link has been sent" in response.json()["msg"]
    mock_pocketbase_service.request_password_reset.assert_called_once_with(
        "test@example.com"
    )


def test_confirm_password_reset_success(client, mock_pocketbase_service):
    """
    Test successfully setting a new password with a valid token.
    """
    # ARRANGE
    mock_pocketbase_service.confirm_password_reset.return_value = (True, None)

    # ACT
    response = client.post(
        "/api/v1/auth/password/reset-confirm",
        json={
            "token": "valid-reset-token",
            "password": "newpassword123",
            "password_confirm": "newpassword123",
        },
    )

    # ASSERT
    assert response.status_code == 200
    assert "Password has been reset successfully" in response.json()["msg"]
    mock_pocketbase_service.confirm_password_reset.assert_called_once()


def test_confirm_password_reset_mismatch(client):
    """
    Test password reset failure when passwords do not match.
    """
    # ACT
    response = client.post(
        "/api/v1/auth/password/reset-confirm",
        json={
            "token": "any-token",
            "password": "newpassword123",
            "password_confirm": "differentpassword",
        },
    )

    # ASSERT
    assert response.status_code == 422
    assert "Passwords do not match" in response.json()["detail"]


# --- Test OAuth Flow ---

def test_get_oauth2_providers(client, mock_pocketbase_service):
    """
    Test the endpoint that lists available OAuth2 providers.
    """
    # ARRANGE: The mock needs to return objects with attributes, not dicts,
    # because the endpoint returns them directly.
    from types import SimpleNamespace
    mock_provider = SimpleNamespace(name="google", auth_url="http://google.com/auth")
    mock_pocketbase_service.get_oauth2_providers.return_value = [mock_provider]
    
    # ACT
    response = client.get("/api/v1/auth/oauth2/providers")
    
    # ASSERT
    assert response.status_code == 200
    # The response serializes the object to a dict, so we compare to a dict.
    assert response.json() == {"providers": [{"name": "google", "auth_url": "http://google.com/auth"}]}


def test_oauth2_callback_success(
    client, mock_pocketbase_service, mock_pocketbase_auth_data
):
    """
    Test the final step of the OAuth2 flow where the code is exchanged for a token.
    """
    # ARRANGE
    mock_pocketbase_service.auth_with_oauth2.return_value = mock_pocketbase_auth_data

    # ACT
    response = client.post(
        "/api/v1/auth/oauth2/google/callback",
        json={
            "code": "auth-code-from-google",
            "code_verifier": "pkce-code-verifier",
            "redirect_uri": "http://localhost:5173/callback",
        },
    )

    # ASSERT
    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "fake-jwt-token"
    mock_pocketbase_service.auth_with_oauth2.assert_called_once()
