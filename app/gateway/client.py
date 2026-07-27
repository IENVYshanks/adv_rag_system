from langchain_openai import ChatOpenAI
from portkey_ai import PORTKEY_GATEWAY_URL, Portkey, createHeaders

from app.config import settings


# Save this template in the Portkey dashboard. The application sends only the
# resulting pc-... slug, because the workspace blocks inline gateway configs.
GATEWAY_CONFIG = {
    "strategy": {"mode": "fallback"},
    "cache": {"mode": "simple"},
    "retry": {
        "attempts": 2,
        "on_status_codes": [429, 503],
    },
    "targets": [
        {
            "override_params": {
                "model": f"@{settings.GROQ_SLUG}/llama-3.3-70b-versatile"
            }
        },
        {
            "override_params": {
                "model": f"@{settings.GROQ_SLUG_2}/llama-3.1-8b-instant"
            }
        },
    ],
}


def _saved_config() -> str | None:
    config_id = settings.PORTKEY_CONFIG_ID
    if not config_id:
        return None
    if not config_id.startswith("pc-"):
        raise RuntimeError(
            "PORTKEY_CONFIG_ID must be a saved Portkey config slug "
            "starting with 'pc-'."
        )
    return config_id


def _portkey_options() -> dict:
    options = {"api_key": settings.PORTKEY_API_KEY}
    config_id = _saved_config()
    if config_id:
        options["config"] = config_id
    return options


portkey_client = Portkey(**_portkey_options())


def get_langchain_llm(feature: str = "rag") -> ChatOpenAI:
    """Return a Portkey-backed LangChain chat model."""
    if not settings.PORTKEY_API_KEY:
        raise RuntimeError(
            "PORTKEY_API_KEY is required to use the application LLM gateway."
        )

    header_options = {
        "api_key": settings.PORTKEY_API_KEY,
        "metadata": {
            "feature": feature,
            "_user": "rag-system",
            "environment": "production",
        },
    }
    config_id = _saved_config()
    if config_id:
        header_options["config"] = config_id

    return ChatOpenAI(
        api_key=settings.PORTKEY_API_KEY,
        base_url=PORTKEY_GATEWAY_URL,
        model=f"@{settings.GROQ_SLUG}/llama-3.3-70b-versatile",
        temperature=0,
        default_headers=createHeaders(**header_options),
    )


def extract_cache_status(response) -> str:
    """Read Portkey's cache status response header when available."""
    for attr in ("_raw_response", "_response", "_http_response"):
        raw = getattr(response, attr, None)
        if raw is not None:
            status = getattr(raw, "headers", {}).get(
                "x-portkey-cache-status",
                "",
            )
            if status:
                return status.upper()
    return "MISS"
