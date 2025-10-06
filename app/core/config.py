import httpx
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
        return response.json()
    except httpx.RequestError as e:
        raise RuntimeError(f"FATAL: Could not fetch remote configuration. Network error: {e}") from e
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"FATAL: Could not fetch remote configuration. Status code: {e.response.status_code}") from e


class Settings(BaseSettings):
    """
    Main settings class. It first loads local bootstrap vars, then fetches
    and validates the remote configuration.
    """
    # --- Step 1: Bootstrap settings loaded from the local .env file ---
    DOTENV_SERVER_URL: str
    DOTENV_SERVER_KEY: str

    # --- Step 2: Settings fetched from the remote server ---
    SECRET_KEY: str = Field(..., alias='FLASK_SECRET_KEY')
    POCKETBASE_URL: str
    POCKETBASE_ADMIN_EMAIL: str
    POCKETBASE_ADMIN_PASSWORD: str
    STRIPE_API_KEY: str
    STRIPE_WEBHOOK_SECRET: str
    GEMINI_API_KEY: str
    ELEVENLABS_API_KEY: str
    RESEND_API_KEY: str # <-- THIS IS THE NEW LINE

    # --- Settings with default values (can be overridden by remote config) ---
    PROJECT_NAME: str = "Bizniz AI"
    API_V1_STR: str = "/api/v1"
    CREDIT_UNIT_NAME: str = "Coin"
    CREDIT_UNIT_NAME_PLURAL: str = "Coins"
    FREE_SIGNUP_COINS: int = 10
    
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra='ignore')


def get_settings() -> Settings:
    """
    Initializes and returns the application settings.
    This function orchestrates the bootstrap and remote fetching process.
    """
    bootstrap_settings = Settings.model_validate({})
    
    remote_config_data = fetch_remote_config(
        url=bootstrap_settings.DOTENV_SERVER_URL,
        api_key=bootstrap_settings.DOTENV_SERVER_KEY
    )
    
    combined_data = {
        **bootstrap_settings.model_dump(),
        **remote_config_data
    }
    
    return Settings.model_validate(combined_data)


# Create the single, globally accessible instance of the settings.
settings = get_settings()