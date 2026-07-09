"""LangGraph agent layer (contract section 9, AGENT_DESIGN.md).

Five focused graphs live in app.agents.graphs; every capability they can
reach is registered in app.agents.tools (read or draft only, enumerated
by the guardrail tests) and every model call flows through the single
seam in app.agents.llm.

Two absolute rules govern everything here:
1. No LLM computes a figure; agents explain and draft around the
   deterministic engine's output, never produce numbers.
2. No send, no file, no payment: agents draft, a person approves, a
   person acts outside the system.
"""

from app.agents import llm, tools

__all__ = ["llm", "tools"]
