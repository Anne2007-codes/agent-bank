from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "sqlite:///./agentbank.db"
    public_base_url: str = "http://localhost:8000"

    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_webhook_id: str = ""
    paypal_force_mock: bool = False
    currency: str = "USD"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    approval_threshold_cents: int = 5000
    per_tx_limit_cents: int = 100000
    daily_limit_cents: int = 250000
    demo_delay_seconds: float = 0.8

    @property
    def paypal_mock(self) -> bool:
        return self.paypal_force_mock or not (self.paypal_client_id and self.paypal_client_secret)


settings = Settings()
