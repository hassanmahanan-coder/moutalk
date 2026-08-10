"""MockLLM（无 key 降级）话术行为测试：确定性 + 多样轮换 + 战术感知。"""


from app.engine.llm import MockLLM

HIGH_PRICE = "[话术生成] 当前战术: time_pressure。\n[用户发言] 对方说: 235 万太高了\n"
BARGAIN = "[话术生成] 当前战术: time_pressure。\n[用户发言] 对方说: 价格再谈 180 万行吗\n"
SILENT_PROMPT = "[话术生成] 当前战术: silence_pressure。\n[用户发言] 对方说: 便宜点吧\n"
BAIT_PROMPT = "[话术生成] 当前战术: concession_bait。\n[用户发言] 对方说: 便宜点吧\n"


async def _utter(prompt: str) -> str:
    return await MockLLM().ainvoke(prompt)


class TestMockYield:
    async def test_same_input_is_deterministic(self):
        assert await _utter(HIGH_PRICE) == await _utter(HIGH_PRICE)

    async def test_price_messages_no_longer_return_same_fixed_line(self):
        """回归：此前「含价格关键词」永远返回同一句固定文案。"""
        assert await _utter(HIGH_PRICE) != await _utter(BARGAIN)

    async def test_tactic_changes_wording_for_same_user_msg(self):
        assert await _utter(SILENT_PROMPT) != await _utter(BAIT_PROMPT)

    async def test_reply_membership_in_safety_pool(self):
        """话术必须来自战术安全模板 ∪ 通用沟通池，不能越界编造报价。"""
        from app.engine.tactics import SAFE_TEMPLATES

        pool = {*SAFE_TEMPLATES["time_pressure"], *MockLLM.GENERIC_UTTERANCES}
        assert await _utter(HIGH_PRICE) in pool