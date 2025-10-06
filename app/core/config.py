import httpx
import json # <-- Import the json library
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

def fetch_remote_config(url: str, api_key: str) -> dict:
    """
    Fetches configuration from your remote secret manager at application startup.
    """
    if not all([url, api_key]):
        raise ValueError("DOTENV_SERVER_URL and DOTENV_SERVER_KEY must be set in the environment.")
    
    headers = {"Authorization": f"Bearer {api_key}"}
    print(f"--> Fetching remote configuration from: {url}")
    
    try:
        response = httpx.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        print("--> Remote configuration fetched successfully.")
        # NEW: Explicitly handle JSON decoding to provide a better error message
        return response.json()
    except httpx.RequestError as e:
        raise RuntimeError(f"FATAL: Could not fetch remote configuration. Network error: {e}") from e
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"FATAL: Could not fetch remote configuration. Status code: {e.response.status_code}") from e
    except json.JSONDecodeError: # <-- CATCH THE SPECIFIC ERROR
        raise RuntimeError(
            "FATAL: Remote config server responded successfully, but the response body was NOT valid JSON. "
            "Please verify the server is returning a correctly formatted JSON object."
        )


# The rest of the file is unchanged.
# --- NEW: A separate class for bootstrapping ---
class BootstrapSettings(BaseSettings):
    """Loads ONLY the variables needed to connect to the remote secret manager."""
    DOTENV_SERVER_URL: str
    DOTENV_SERVER_KEY: str
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra='ignore')


class Settings(BaseSettings):
    """
    The main settings class that holds the complete, validated application configuration.
    """
    DOTENV_SERVER_URL: str
    DOTENV_SERVER_KEY: str
    SECRET_KEY: str = Field(..., alias='FLASK_SECRET_KEY')
    POCKETBASE_URL: str
    POCKETBASE_ADMIN_EMAIL: str
    POCKETBASE_ADMIN_PASSWORD: str
    STRIPE_API_KEY: str
    STRIPE_WEBHOOK_SECRET: str
    GEMINI_API_KEY: str
    ELEVENLABS_API_KEY: str
    RESEND_API_KEY: str
    PROJECT_NAME: str = "Bizniz AI"
    API_V1_STR: str = "/api/v1"
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
        url=bootstrap_conf.DOTENV_SERVER_URL,
        api_key=bootstrap_conf.DOTENV_SERVER_KEY
    )
    combined_data = {
        **bootstrap_conf.model_dump(),
        **remote_config_data
    }
    return Settings.model_validate(combined_data)

settings = get_settings()