from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str

    apple_team_id: str = ""
    apple_client_id: str = ""
    apple_key_id: str = ""
    apple_private_key_path: str = ""

    session_jwt_secret: str
    session_jwt_algorithm: str = "HS256"
    session_jwt_ttl_seconds: int = 2592000

    # Fernet key (Fernet.generate_key()) used to encrypt aggregator access
    # tokens at rest. Dev-only placeholder -- swap for a secrets-manager-backed
    # key before this ever touches real bank credentials.
    token_encryption_key: str

    plaid_client_id: str = ""
    plaid_secret: str = ""
    plaid_env: str = "sandbox"  # sandbox | production
    plaid_webhook_secret: str = ""

    # Which backend app/agent/claude_agent.py's tool-use loop talks to (see
    # app/agent/agent_client.py). "openrouter" is the default -- routes to
    # OPENROUTER_MODEL via openrouter.ai using OPENROUTER_API_KEY.
    # "anthropic" talks to Claude's native Messages API directly via the keys
    # below. "openai_compatible" talks to any other /chat/completions-shaped
    # endpoint (DeepSeek, Kimi/Moonshot, GPT-5-mini, ...) via
    # agent_api_key/agent_model/agent_base_url -- handy for cheap local
    # prototyping without an OpenRouter or Anthropic key at all.
    agent_provider: str = "openrouter"  # openrouter | anthropic | openai_compatible

    openrouter_api_key: str = ""
    openrouter_model: str = "deepseek/deepseek-v4-flash-0731"
    openrouter_site_url: str = ""
    openrouter_app_name: str = "Bankr"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    agent_api_key: str = ""
    agent_model: str = "deepseek-chat"
    agent_base_url: str = "https://api.deepseek.com"

    apns_key_id: str = ""
    apns_team_id: str = ""
    apns_auth_key_path: str = ""
    apns_topic: str = ""
    apns_use_sandbox: bool = True


settings = Settings()
