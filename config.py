# app/core/config.py

import httpx
from pydantic import Field, AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


def fetch_remote_config(url: str, api_key: str) -> dict:
    """Fetches configuration from a remote secret manager at startup."""
    if not all([url, api_key]):
        raise ValueError("DOTENV_SERVER_URL and DOTENV_SERVER_KEY must be set.")
    headers = {"Authorization": f"Bearer {api_key}"}
    print(f"--> Fetching remote configuration from: {url}")
    try:
        response = httpx.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        print("--> Remote configuration fetched successfully.")
        return response.json()
    except Exception as e:
        raise RuntimeError(
            f"FATAL: Could not fetch remote configuration. Error: {e}"
        ) from e


class BootstrapSettings(BaseSettings):
    """Loads only the variables needed to connect to the remote secret manager."""

    DOTENV_SERVER_URL: str
    DOTENV_SERVER_KEY: str
    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=True, extra="ignore"
    )


class Settings(BaseSettings):
    """
    The main settings class that holds the complete, validated application configuration.
    """

    # --- Core Infrastructure ---
    DOTENV_SERVER_URL: str
    DOTENV_SERVER_KEY: str
    SECRET_KEY: str = Field(
        ..., description="Used for signing internal tokens/data. Critical for security."
    )
    POCKETBASE_URL: str
    POCKETBASE_ADMIN_EMAIL: str
    POCKETBASE_ADMIN_PASSWORD: str

    # --- Frontend URL ---
    # This is the base URL of your separate frontend application (e.g., SvelteKit, React).
    # It's used by the backend to construct URLs for emails (e.g., verification, password reset links).
    # Example: "http://localhost:5173" for dev or "https://www.yourapp.com" for prod.
    FRONTEND_URL: AnyHttpUrl

    # --- Third-Party API Keys ---
    STRIPE_API_KEY: str
    STRIPE_WEBHOOK_SECRET: str
    GEMINI_API_KEY: str
    ELEVENLABS_API_KEY: str
    RESEND_API_KEY: str
    INTERNAL_API_SECRET_TOKEN: str

    # --- Application Metadata ---
    PROJECT_NAME: str = "bugswriter.ai"
    API_V1_STR: str = "/api/v1"

    # --- Credit System ---
    CREDIT_UNIT_NAME: str = "Coin"
    CREDIT_UNIT_NAME_PLURAL: str = "Coins"
    FREE_SIGNUP_COINS: int = 10


def get_settings() -> Settings:
    """
    Initializes and returns the application settings by combining local
    bootstrap variables with remotely fetched secrets.
    """
    bootstrap_conf = BootstrapSettings()
    remote_config_data = fetch_remote_config(
        url=bootstrap_conf.DOTENV_SERVER_URL, api_key=bootstrap_conf.DOTENV_SERVER_KEY
    )
    combined_data = {**bootstrap_conf.model_dump(), **remote_config_data}
    return Settings.model_validate(combined_data)


settings = get_settings()
