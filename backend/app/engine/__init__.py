"""谈判引擎（多 Agent 状态机）。"""

from app.engine.engine import NegotiationEngine, build_llm
from app.engine.nodes import MAX_RETRY, check_bottom_lines, extract_dim_value
from app.engine.state import NegotiationState

__all__ = [
    "MAX_RETRY",
    "NegotiationEngine",
    "NegotiationState",
    "build_llm",
    "check_bottom_lines",
    "extract_dim_value",
]
