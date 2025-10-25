from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Core App Settings
    SECRET_KEY: str
    PROJECT_NAME: str = "Munni AI"
    API_V1_STR: str = "/api/v1"

    # PocketBase Settings
    POCKETBASE_URL: str
    POCKETBASE_ADMIN_EMAIL: str
    POCKETBASE_ADMIN_PASSWORD: str

    # Stripe Settings
    STRIPE_API_KEY: str
    STRIPE_WEBHOOK_SECRET: str

    # Third-Party API Keys
    GEMINI_API_KEY: str
    ELEVENLABS_API_KEY: str

    # Branding & Pricing
    CREDIT_UNIT_NAME: str = "Coin"
    CREDIT_UNIT_NAME_PLURAL: str = "Coins"
    FREE_SIGNUP_COINS: int = 10

    # Pydantic settings configuration
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


# Create a single, globally accessible instance of the settings
settings = Settings()
