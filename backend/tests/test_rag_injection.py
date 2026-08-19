"""RAG 注入话术生成测试：相似历史参考进入 prompt（PRD 8.3 第 5 步）。"""

from app.engine.nodes import build_graph, utterance_node
from app.scenarios import load_scenario


class FakeLLM:
    configured = True

    def __init__(self):
        self.calls = []
        self.light_calls = []

    async def ainvoke(self, prompt: str, *, light: bool = False) -> str:
        if light:
            self.light_calls.append(prompt)
            return '{"intent_type": "offer", "price": 200}'
        self.calls.append(prompt)
        return "报价：185 万。"

    async def ainvoke_json(self, prompt: str, *, light: bool = False) -> dict:
        self.light_calls.append(prompt)
        return {"intent_type": "offer", "price": 200}


class FakeRAG:
    """返回固定历史片段的假 RAG 记忆。"""

    def __init__(self, results):
        self.results = results
        self.queries = []

    def search(self, scenario_id: str, query: str, top_k: int = 3, role: str | None = None) -> list[dict]:
        self.queries.append((scenario_id, query, top_k, role))
        return self.results


def _state(**overrides):
    state = {
        "scenario": load_scenario("it_procurement"),
        "scenario_id": "it_procurement",
        "user_message": "报价 200 万可以吗？",
        "selected_tactic": "time_pressure",
        "tactic_sub_role": None,
        "retry_reason": None,
        "history": [
            {"role": "user", "content": "第一次询价"},
            {"role": "assistant", "content": "报价 235 万"},
        ],
        "round": 2,
    }
    state.update(overrides)
    return state


async def test_rag_results_injected_into_prompt():
    rag = FakeRAG(
        [
            {"text": "客户要求降价时我们通常这样回应", "role": "assistant", "distance": 0.9},
            {"text": "可以申请总裁特批", "role": "assistant", "distance": 0.7},
        ]
    )
    llm = FakeLLM()
    await utterance_node(_state(), llm, rag=rag)
    prompt = llm.calls[0]
    assert "[历史参考]" in prompt
    assert "客户要求降价时我们通常这样回应" in prompt
    assert "可以申请总裁特批" in prompt


async def test_rag_query_uses_scenario_and_user_msg():
    rag = FakeRAG([])
    llm = FakeLLM()
    await utterance_node(_state(), llm, rag=rag)
    assert rag.queries
    sid, query, top_k, role = rag.queries[0]
    assert sid == "it_procurement"
    assert "报价 200 万可以吗？" in query
    assert top_k == 3
    assert role == "assistant", "话术生成应只取助手应答作参考（防回显）"


async def test_user_message_never_injected_as_reference():
    """回归（回显 bug）：即使 RAG 返回用户消息，也不得注入话术 prompt。"""
    rag = FakeRAG(
        [
            {"text": "235 太贵了，200 万可以吗", "role": "user", "distance": 0.9},
            {"text": "可以谈，220 万包含三年原厂服务", "role": "assistant", "distance": 0.8},
        ]
    )
    llm = FakeLLM()
    await utterance_node(_state(), llm, rag=rag)
    prompt = llm.calls[0]
    assert "235 太贵了，200 万可以吗" not in prompt, "用户消息不得作为'应答参考'注入"


async def test_no_rag_keeps_prompt_unchanged():
    llm = FakeLLM()
    await utterance_node(_state(), llm, rag=None)
    assert "[历史参考]" not in llm.calls[0]


async def test_empty_rag_results_no_section():
    llm = FakeLLM()
    await utterance_node(_state(), llm, rag=FakeRAG([]))
    assert "[历史参考]" not in llm.calls[0]


async def test_build_graph_accepts_rag():
    rag = FakeRAG([])
    graph = build_graph(FakeLLM(), rag=rag)
    assert graph is not None
