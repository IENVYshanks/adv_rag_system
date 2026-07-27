from __future__ import annotations

import threading

import logfire
from nemoguardrails import LLMRails, RailsConfig
from nemoguardrails.integrations.langchain.llm_adapter import LangChainLLMAdapter

from app.gateway import get_langchain_llm
from app.guardrails.colang_rules import (
    COLANG_CONTENT,
    RAIL_INDICATORS,
    YAML_CONTENT,
)

_rails: LLMRails | None = None
_rails_lock = threading.Lock()


def initialize_rails() -> LLMRails:
    """Initialize the shared NeMo Guardrails runtime once."""
    global _rails
    if _rails is not None:
        return _rails

    with _rails_lock:
        if _rails is None:
            config = RailsConfig.from_content(
                colang_content=COLANG_CONTENT,
                yaml_content=YAML_CONTENT,
            )
            _rails = LLMRails(
                config=config,
                llm=LangChainLLMAdapter(
                    get_langchain_llm(feature="guardrails")
                ),
            )
            logfire.info("NeMo Guardrails initialized")
    return _rails


def guard(user_input: str) -> tuple[bool, str | None]:
    """Return whether a rail handled the input and its safe response."""
    rails = initialize_rails()
    with logfire.span("Guardrails input check"):
        response = rails.generate(messages=[{"role": "user", "content": user_input}])

    if isinstance(response, dict):
        content = str(response.get("content", ""))
    else:
        content = str(response)

    normalized = content.lower()
    fired = any(indicator in normalized for indicator in RAIL_INDICATORS)
    return fired, content if fired else None
