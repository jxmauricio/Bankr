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
    # Lifetime of tokens minted by POST /auth/mcp-token for external MCP
    # clients. Long by default (1 year) since they're pasted into a client
    # config once; re-mint to rotate.
    mcp_token_ttl_seconds: int = 31536000

    # Fernet key (Fernet.generate_key()) used to encrypt aggregator access
    # tokens at rest. Dev-only placeholder -- swap for a secrets-manager-backed
    # key before this ever touches real bank credentials.
    token_encryption_key: str

    plaid_client_id: str = ""
    plaid_secret: str = ""
    plaid_env: str = "sandbox"  # sandbox | production
    # No PLAID_WEBHOOK_SECRET setting: unlike most webhook senders, Plaid
    # doesn't sign with a static shared secret. It signs with a JWT whose
    # public key is fetched live via webhook_verification_key_get using
    # plaid_client_id/plaid_secret above -- see
    # PlaidClient.verify_webhook_signature.
    # Public URL for POST /webhooks/plaid, attached to every newly-linked
    # Item. Blank is a valid, fully-functional choice (sync still runs via
    # the Refresh button and on link) -- see backend/README.md "Plaid webhooks".
    plaid_webhook_url: str = ""

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

    # Extended/reasoning thinking before the model answers -- catches
    # arithmetic/multi-step slips before they reach the user, at the cost of
    # latency and tokens. Only wired up for "anthropic" (Claude's native
    # thinking param) and "openrouter" (its unified `reasoning` param, which
    # only does something if the selected OPENROUTER_MODEL itself supports
    # reasoning) -- "openai_compatible" is a passthrough to an arbitrary
    # endpoint, so it's left alone; point AGENT_MODEL at a reasoning model
    # directly (e.g. deepseek-reasoner) if you want that there instead.
    agent_extended_thinking: bool = False
    agent_thinking_budget_tokens: int = 2048

    # Web search tool the agent can call for anything time-sensitive (current
    # rates, inflation, ...) it wasn't trained on -- see
    # app/integrations/web_search.py. Optional: with no key set, calling the
    # web_search tool returns a clear error result instead of live results,
    # same "degrade gracefully" pattern as the agent providers above.
    brave_search_api_key: str = ""

    # Where "today" / "this month" / "last week" are anchored for a user
    # whose client hasn't reported a timezone yet (see User.timezone).
    default_timezone: str = "America/New_York"

    apns_key_id: str = ""
    apns_team_id: str = ""
    apns_auth_key_path: str = ""
    apns_topic: str = ""
    apns_use_sandbox: bool = True


settings = Settings()
