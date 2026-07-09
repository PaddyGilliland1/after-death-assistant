"""The single LLM seam for every agent graph.

All model access flows through call_llm so tests can monkeypatch one
function and no graph builds its own client. The model is only used to
EXPLAIN and DRAFT prose; it never computes a figure (design rule 1) and
nothing here can send, file or pay (design rule 2).

When ANTHROPIC_API_KEY is not configured, llm_enabled() is False and the
LLM-dependent endpoints return 503; the deterministic paths (forms_draft
field mapping, next_actions suggestions) keep working in full.
"""

from typing import Any

from app.core.config import Settings, get_settings

AGENT_MODEL = "claude-sonnet-5"


class LLMUnavailableError(RuntimeError):
    """Raised when an LLM call is attempted without a configured key."""


def llm_enabled(settings: Settings | None = None) -> bool:
    """Whether the Anthropic key is configured."""
    settings = settings or get_settings()
    return bool(settings.ANTHROPIC_API_KEY.strip())


def get_llm(settings: Settings | None = None) -> Any:
    """Build the ChatAnthropic client (langchain-anthropic).

    Imported lazily so environments without a key never touch the SDK.
    """
    settings = settings or get_settings()
    if not llm_enabled(settings):
        raise LLMUnavailableError(
            "ANTHROPIC_API_KEY is not configured; LLM-dependent agent graphs "
            "are unavailable."
        )
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=AGENT_MODEL,
        api_key=settings.ANTHROPIC_API_KEY,
        max_tokens=2048,
        timeout=60,
    )


def call_llm(system_prompt: str, user_prompt: str, settings: Settings | None = None) -> str:
    """Invoke the model with a system and a user prompt; return plain text.

    This is THE seam: tests monkeypatch app.agents.llm.call_llm and no
    network is ever reached. Graphs must call it via the module attribute
    (llm.call_llm), never bind it at import time.
    """
    model = get_llm(settings)
    response = model.invoke([("system", system_prompt), ("human", user_prompt)])
    content = response.content
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return str(content)
