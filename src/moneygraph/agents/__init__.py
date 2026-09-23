"""Agent layer.

Every agent here sits *around* the deterministic core, never inside it. None of
them assigns a role, a score, a cluster or a rank — those come from the rule
engine (`roles.py`), Louvain (`clustering.py`) and the weighted sum
(`priority.py`). The brief forbids a "black box" role, so the agents do what an
LLM is genuinely better at: reading an unfamiliar schema, phrasing a rule trace
in readable English, answering an analyst's question by calling graph
functions, and writing up what data is missing.

Every one of them degrades to a deterministic path when there is no API key,
when the budget runs out, or when its output fails validation.
"""

from .llm import LLMClient, load_env

__all__ = ["LLMClient", "load_env"]
