# 谋谈 MouTalk 谈判 Agent 流程图

> 与 `backend/app/engine/nodes.py::build_graph()` 代码一一对应（LangGraph StateGraph）。

## 1. 图结构总览（单轮）

```mermaid
flowchart TD
    START([START]) --> intent[意图解析 intent_node]
    intent --> tactic[战术选择 tactic_node]
    tactic --> utterance[话术生成 utterance_node]
    utterance --> bottom_line[底线检查 bottom_line_node]

    bottom_line -->|通过 ok| END([END])
    bottom_line -->|越线 retry_count ≤ 3| utterance
    bottom_line -->|越线 retry_count > 3| fallback[安全话术 fallback_node]
    fallback --> END

    subgraph RAG["RAG 记忆（可选）"]
        rag[(Milvus\n检索 top-3)]
    end
    utterance -. 检索 [历史参考] .-> rag
    rag -. 相似应答 .-> utterance

    subgraph LLM["LLM（GLM / Mock）"]
        l1[light: 意图解析 + 战术兜底]
        l2[主模型: 话术生成]
    end
    intent -. ainvoke_json .-> l1
    tactic -. ainvoke_json 兜底 .-> l1
    utterance -. ainvoke .-> l2
```

## 2. 节点明细

| 节点 | 函数 | 输入 | 输出 |
|---|---|---|---|
| intent | `intent_node` (nodes.py:95) | 用户消息 | intent（intent_type/price/concessions/emotion/aggression_level），LLM 失败走规则兜底 `rule_intent` |
| tactic | `tactic_node` (nodes.py:108) | 阶段+意图+战术上下文 | selected_tactic/tactic_reason/tactic_sub_role/tactic_context |
| utterance | `utterance_node` (nodes.py:164) | 战术提示+历史+RAG 参考 | reply（回复文本） |
| bottom_line | `bottom_line_node` (nodes.py:237) | 回复+场景底线 | reply_blocked/retry_reason/bottom_line_status/opponent_offer |
| fallback | `fallback_node` (nodes.py:263) | 场景安全模板 | reply（模板轮换，不越线） |

## 3. 底线检查重试流程

```mermaid
flowchart LR
    A[话术回复] --> B{提取数值\n提取维度值}
    B -->|未命中关键字| OK[通过]
    B -->|越线| C{retry_count ≤ 3?}
    C -->|是| R[携带驳回原因\n重回话术生成] --> A
    C -->|否| F[安全话术模板\nfallback] --> END([END])
```

- `MAX_RETRY = 3`（nodes.py:26），第 4 次越线转安全模板
- 驳回原因注入重试 prompt（`[上轮被驳回] 驳回原因: ...`，nodes.py:173）
- 纯规则检查：`check_bottom_lines`（nodes.py:220），关键词 + 单位解析，无 LLM

## 4. 战术决策（tactics.py）

规则引擎 `select_tactic(ctx)` 优先；未命中且 LLM 已配置时走 LLM 兜底（nodes.py:124），再兜底 `neutral`：

```mermaid
flowchart TD
    T[规则引擎 select_tactic] --> H{命中?}
    H -->|是| U[选用战术]
    H -->|否| L{LLM 已配置?}
    L -->|是| F[LLM 兜底\nTACTIC_FALLBACK_PROMPT]
    L -->|否| N[neutral 中性回应]
    F --> U
```

10 种战术（8 常规 + 僵局打破 + 中性兜底）：

- 红脸白脸（多步，最多 2 轮）· 时间压迫 · 最后通牒 · 虚假底线
- 分而治之 · 沉默施压 · 让步诱饵 · 信息不对称 · 打破僵局 · 中性回应

## 5. 单轮时序（含持久化）

```mermaid
sequenceDiagram
    participant U as 用户
    participant WS as WebSocket 端点
    participant G as LangGraph 引擎
    participant CP as PostgresSaver
    participant R as RAG

    U->>WS: user_msg
    WS->>G: engine.run_round(state, text, thread_id)
    G->>G: intent → tactic → utterance → bottom_line
    G-->>R: 检索 [历史参考]（utterance 内）
    R-->>G: top-3 相似应答
    alt 越线且未超 3 次
        G->>G: 重回 utterance（带驳回原因）
    else 越线超 3 次
        G->>G: fallback 安全话术
    end
    G->>CP: checkpoint 保存状态
    G-->>WS: 新 state
    WS-->>U: token 流式 + meta
    WS->>R: add_round(user/assistant) 写入记忆
```

## 6. 阶段推导（derive_phase）

```mermaid
flowchart TD
    S{round} -->|1| O[opening 开场]
    S -->|rounds_since_last_progress > 3| D[deadlock 僵局]
    S -->|其他| C[core 核心]
```

（nodes.py:72-78，战术选择与僵局打破均依赖该阶段）
