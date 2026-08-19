# 谋谈（MouTalk）项目讲解稿 —— 面试与技术问答指南

> **定位**：用于项目面试讲解与技术问答的全栈深度文档。
> **用法**：第 1 章为 10-15 分钟完整讲解稿（可背诵）；第 2-7 章为各模块技术深挖素材；第 8 章为高频面试题速答。
> **配套**：需求文档 `docs/negotiation-agent-prd.md`（v3.0 + 附录 C）、问题记录 `docs/troubleshooting.md`（54 条）。

---

## 目录

1. [项目讲解稿（10-15 分钟）](#1-项目讲解稿10-15-分钟)
2. [需求与产品形态](#2-需求与产品形态)
3. [技术选型与理由](#3-技术选型与理由)
4. [系统架构](#4-系统架构)
5. [核心业务流程（讲透这 5 条链路）](#5-核心业务流程)
6. [关键设计决策与难点攻坚（面试亮点）](#6-关键设计决策与难点攻坚)
7. [测试体系与工程质量](#7-测试体系与工程质量)
8. [高频面试题速答（Q&A）](#8-高频面试题速答qa)

---

## 1. 项目讲解稿（10-15 分钟）

> 面试自我介绍/项目讲解时的完整话术框架。每段标注建议时长与要点。

### 1.1 开场：项目是什么（30 秒）

> "我独立设计并开发了一个**多轮深度谈判模拟 Agent**——谋谈（MouTalk）。用户可以扮演采购、求职者等角色，与一个由大语言模型驱动的 AI 对手进行多轮商务谈判。系统会实时识别用户的谈判意图、判断是否突破底线、动态切换 8 种谈判战术，并在谈判结束后生成一份包含客观评分与 LLM 主观点评的复盘报告，还支持历史对比、趋势曲线和 PDF 下载。"

**一句话总结**：一个 LLM Agent 驱动的、带完整商业闭环（认证-谈判-报告-支付-管理后台）的谈判模拟 SaaS。

### 1.2 技术栈总览（1 分钟）

> "前端 Vue 3 + Vite + Element Plus + Pinia + ECharts；后端 FastAPI + LangGraph 编排 Agent 状态机，Celery 做异步任务，PostgreSQL 存业务数据，Redis 做缓存/锁/限流/事件总线，Milvus 做谈判历史向量记忆，LLM 用 DeepSeek V4 Flash（opencode 网关，无密钥自动降级 MockLLM），LangFuse 做可观测，支付宝沙箱支付，Docker Compose + GitHub Actions 部署。全栈共 477 个后端测试通过（+2 skipped）、21 个前端测试、4 个 E2E 测试。"

### 1.3 系统架构（2 分钟）

> "整体是前后端分离 + WebSocket 实时通信。核心是**谈判引擎**——一个基于 LangGraph 的 5 节点状态机：**意图解析 → 战术选择 → 话术生成 → 底线检查 → 兜底回退**（其中底线→兜底是条件边：突破底线时重试或走兜底）。用户通过 WebSocket 发送消息，引擎单轮驱动状态机，LLM 流式生成回复，逐 token 转发给前端。每轮结束后，会话状态通过 PostgresSaver 持久化到 PostgreSQL，支持断线续谈；对话内容向量化存入 Milvus，下一轮用 RAG 检索相关历史注入上下文。复盘报告由 Celery 异步生成，完成后通过 Redis 事件总线桥接推送到用户的 WebSocket。"

### 1.4 核心亮点一：谈判引擎（2 分钟）

> "这个引擎最难的是让 AI 对手'有策略'而不是乱聊。我的设计分三层：
> 第一层**意图解析**——用轻量模型把用户发言结构化，提取意图类型（报价/拒绝/询问/让步）、价格数值、情绪、攻击性；
> 第二层**战术选择**——优先用 Python 规则决策表（纯规则毫秒级、零成本）从 8 种谈判战术中选招，规则未命中时让 LLM 兜底选；
> 第三层**底线约束**——每个场景的每个维度（价格/交付/质保等）都有明确底线值与方向（min=不低于底线，max=不高于上限），AI 话术生成后做数值提取与底线比对，**AI 的让步不得越过底线**；突破底线就重试最多 3 次，仍不行就发安全话术，保证 AI 对手永远不无底线退让。用户报价是否逼近 AI 底线，也作为复盘客观分的评分依据。"

### 1.5 核心亮点二：断线续谈与 RAG 记忆（1.5 分钟）

> "谈判可能长达几十分钟，用户可能随时断网。我用了两层保障：**PostgresSaver 做图状态持久化**——每一轮的完整状态存进 PostgreSQL，重连后用同一 thread_id 恢复状态；**Redis 缓冲队列**——AI 回复先写入缓冲，前端 ack 后才删除，重连时通过 resume/replay 协议把断线期间的消息补回来。
另外，谈判历史会向量化存进 Milvus，配合 BGE embedding 和 Reranker 重排，把相似历史片段注入到下一轮的话术生成上下文，让 AI 对手'记得'自己之前说过什么承诺。"

### 1.6 核心亮点三：双轨复盘报告（1.5 分钟）

> "报告分两条线：**客观分**是纯规则计算——让步幅度、底线贴近度、战术命中、谈判时长，可复现可解释；**主观分**由 LLM Judge 对谈判质量打分。总分按 0.6 客观 + 0.4 主观归一化合成。报告包含双轨得分曲线、8 种战术命中统计、弱点分析、AI 改进建议。生成走 Celery 异步，完成后实时推送通知，支持历史报告对比和 PDF 导出。"

### 1.7 核心亮点四：实时性与工程健壮性（1.5 分钟）

> "实时性方面：WebSocket 真流式（LLM astream 逐 token 转发）；Redis 分布式锁防止同一会话并发调用（429 拒绝）；LLM 令牌桶限流防止单个用户打爆成本（5 次/分钟）；连接管理器统一管理所有 WS 连接，优雅关闭时广播通知。
健壮性方面：LLM 调用失败不静默断连，向用户发送 ENGINE_ERROR 提示并保持连接；Windows 环境下 PostgresSaver 不可用自动降级 JSON 持久化，保证任何环境都能跑通全流程。"

### 1.8 工程化与测试（1 分钟）

> "测试先行是我这个项目的主要开发方式：后端 477 个测试通过（+2 skipped）覆盖引擎/WS/支付/认证/权限等全部模块，前端 vitest 21 例 + Playwright E2E 4 例，CI 里还有 alembic 迁移漂移检查、ruff lint、部署资产守卫。Alembic 管理 7 个数据库迁移，全部经过真实数据库演练。遇到的问题全部记录在 troubleshooting 文档（54 条），形成可追溯的工程资产。"

### 1.9 收尾（30 秒）

> "总结一下这个项目的三个关键词：**LLM Agent 编排**（LangGraph 状态机 + 流式 + RAG）、**高并发实时架构**（WebSocket + Redis 锁/限流/事件总线）、**完整商业闭环**（认证-额度-支付-通知-管理后台）。它不是一个 demo，而是一个可以上线运营的完整产品。"

---

## 2. 需求与产品形态

### 2.1 产品定位
多轮深度谈判模拟 Agent：用户扮演谈判一方，AI 扮演有策略的对手，通过多轮对话达成（或不达成）交易，获得复盘提升。

### 2.2 用户故事（PRD v3.0）
| 故事 | 内容 | 状态 |
|---|---|---|
| 1 | 注册登录（邮箱验证码/JWT/锁定） | ✅ |
| 2 | 发起谈判（3 个官方场景 + 用户自定义场景） | ✅ |
| 3 | 多轮谈判（8 战术/底线约束/流式/教练） | ✅ |
| 4 | 复盘报告（双轨评分/对比/PDF） | ✅ |
| 5 | 订阅支付（免费额度 5 次/月/场景 → Pro/场景包） | ✅ |

### 2.3 商业化模型
- **免费层**：每月每场景 5 次谈判（Redis Lua 原子计数）
- **Pro 订阅**：199 元/30 天，无限谈判 + 完整趋势
- **场景包单买**：88-129 元/个
- 支付：支付宝（RSA2 验签 + 幂等 + 主动对账），开发环境提供"一键直付"演示模式

---

## 3. 技术选型与理由

| 层 | 选型 | 选型理由（面试话术） |
|---|---|---|
| 前端 | Vue 3 + Vite + Element Plus + Pinia + ECharts | 组合式 API + 响应式适合复杂实时 UI；生态成熟 |
| 后端 | FastAPI | 原生 async 契合 WebSocket/流式；Pydantic 校验 |
| Agent 编排 | LangGraph | 显式状态机，节点可复用可测试；PostgresSaver 断点续谈 |
| 异步任务 | Celery + Redis | 报告生成/PDF 导出等耗时任务解耦；broker 不可用降级同步 |
| 业务库 | PostgreSQL 16 | 关系型 + JSONB 存配置型数据 |
| 缓存/锁 | Redis | 分布式锁（SET NX）、令牌桶限流（Lua）、断线缓冲、事件总线 |
| 向量库 | Milvus（Lite/完整版） | 谈判历史相似检索（RAG） |
| Embedding | bge-small-zh（512 维） | BGE-M3 CPU 上 9s/条太慢，bge-small-zh 15ms（实测） |
| 重排 | bge-reranker-base | Milvus top-10 → 精排 → top-3 |
| LLM | DeepSeek V4 Flash（opencode 网关，LLM_API_KEY） | 无密钥自动降级 MockLLM，测试全功能可跑 |
| 可观测 | LangFuse Cloud | LLM 调用链路追踪 |
| 支付 | 支付宝开放平台（RSA2） | 沙箱 + 正式双模式 |
| 部署 | Docker Compose + GitHub Actions + Caddy | 一键起全栈；HTTPS；备份脚本 |

### 关键调整与教训
- **BGE-M3 → bge-small-zh**：性能预算驱动（embedding <200ms），小模型 15ms 达标。
- **LangChain → 官方 SDK 裸管线**：RAG 链路业务定制多，裸管线控制力更强。
- **uvicorn 0.36+ Windows ProactorEventLoop**：psycopg async 不兼容，最终设计为"超时快速降级 JSON 持久化"而非强行换事件循环（见难点 6.6）。

---

## 4. 系统架构

### 4.1 架构总览（分层图）

```
┌─────────────────────────────────────────────────────────┐
│ 前端 (Vue3 + Vite)                                       │
│  LobbyView / RoomView / ReportsView / AdminView ...      │
│  状态: Pinia  auth store   UI: Element Plus + ECharts     │
└──────────────┬──────────────────────────┬────────────────┘
               │ REST (JWT)               │ WebSocket
               ▼                          ▼
┌─────────────────────────────────────────────────────────┐
│ 后端 FastAPI (uvicorn :8765)                             │
│  ├─ api/        auth scenarios sessions negotiation      │
│  │              reports payment notifications admin      │
│  ├─ engine/     LangGraph 状态机 (intent→tactic→utter→    │
│  │              bottom_line→fallback) + LLM 抽象         │
│  └─ services/   session_store quota payment security    │
│                 rag event_bus ws_manager ...            │
└──────┬──────────┬──────────┬──────────┬───────┬─────────┘
       ▼          ▼          ▼          ▼       ▼
   PostgreSQL  Redis  Milvus  Celery Worker  LangFuse
   (业务+图状态) (锁/限流/   (向量记忆)  (报告/PDF)  (LLM 追踪)
                 缓冲/事件总线)
```

### 4.2 数据模型（核心表）
| 表 | 关键字段 | 说明 |
|---|---|---|
| users | email/username/password_hash(bcrypt)/role/is_admin/banned | 三级角色 free/pro/enterprise |
| scenarios | id/title/config_json(JSONB)/price/on_sale/owner_id | 官方内置 owner_id=null；自定义场景属用户 |
| sessions | user_id/scenario_id/status/messages_json | 谈判会话，回放数据源 |
| reports | session_id/total_score/objective_json/subjective_json | 双轨评分存储 |
| orders | out_trade_no/status/amount/type | 支付订单 |
| payment_log | UNIQUE(out_trade_no, trade_no) | 幂等防重 |
| notifications | user_id/type/read_at | 通知体系 |
| admin_audit_log | admin_id/action/target_id | 管理审计 |
| checkpoints（LangGraph） | thread_id/state | 断点续谈 |

### 4.3 关键代码路径（面试可指路）
```
backend/app/
├── engine/            # 谈判引擎（项目灵魂）
│   ├── engine.py      # NegotiationEngine 门面：单轮驱动
│   ├── nodes.py       # 5 节点状态机（intent/tactic/utterance/bottom_line/fallback）
│   ├── tactics.py     # 8 战术规则引擎 + 优先级决策表
│   ├── extractor.py   # 数值提取（LLM 结构化 + 正则兜底 + 中文数字）
│   ├── llm.py         # BaseLLM 抽象 + OpenAIClient + MockLLM + 真流式 astream
│   ├── state.py       # NegotiationState（TypedDict）
│   └── checkpointer.py# PostgresSaver 封装（超时降级）
├── api/negotiation.py # WebSocket 端点：连接/鉴权/流式转发/断线缓冲/报告提交
├── services/rag.py    # Milvus + embedding + reranker 记忆管线
├── services/report_service.py  # 双轨评分 + 趋势 + 对比
├── services/payment_service.py # 订单/回调/幂等/对账/事件发布
└── services/event_bus.py       # Redis pub/sub：worker → API → WS
```

---

## 5. 核心业务流程

### 5.1 一次谈判轮次（最重要，必讲）

```
用户输入
  │ WebSocket /api/negotiation/{session_id}
  ▼
[1] intent_node       LLM 轻量调用 → {intent_type, price, concessions, emotion}
  ▼
[2] tactic_node       rules.select_tactic(state)   ← 纯规则毫秒级
  │                   ├─ 命中 → 8 战术之一（含 tactic_context 跨轮状态）
  │                   └─ 未命中 → LLM 兜底选战术
  ▼
[3] utterance_node    LLM 生成话术（带角色/战术提示/历史/RAG 注入）
  │                   真流式：astream 逐 token → ws.send token
  ▼
[4] bottom_line_node  数值提取（extractor）→ 与场景各维度底线比对
  │                   ├─ 未突破 → 通过
  │                   └─ 突破   → 重试 ≤3 次 → 仍不行 → fallback_node 发安全话术
  ▼
[图外] _finalize_round  写 history/tactic/bottom_line_status → PostgresSaver 存状态
  ▼
  回复全量完成后：meta 推送（tactic/bottom_line/round/score）
  + RAG 写入（user/assistant 各一条向量）
  + save_round 落库（回放数据源，messages_json 偶数=用户/奇数=AI）
```

### 5.2 WebSocket 协议
| 客户端 → 服务端 | 说明 |
|---|---|
| `{"type":"user_msg","text":"..."}` | 用户发言 → 触发一轮引擎 |
| `{"type":"ping"}` / `{"type":"ack"}` | 心跳 / 确认已收到缓冲消息 |
| `{"type":"resume"}` | 重连后拉取断线期间消息 |
| `{"type":"coach"}` | 教练模式：生成建议（不写入历史） |
| `{"type":"end_negotiation"}` | 结束谈判 → 简版结果 + 提交报告生成 |

| 服务端 → 客户端 | 说明 |
|---|---|
| `opening` / `history` | 连接即发（开场白或历史恢复） |
| `token` | LLM 流式分片 |
| `meta` | 战术/底线状态/轮次/实时分数 |
| `simple_result` | 结束时简版结果 |
| `report_ready` / `report_submitted` | 报告完成/已提交异步生成 |
| `engine_error` | 引擎异常提示（不断连） |

### 5.3 断线续谈（两阶段）
1. **状态持久化**：LangGraph PostgresSaver 每轮落 checkpoint（thread_id=session_id）；重连 `restore_state` 恢复。
2. **消息缓冲**：`WsBuffer`（Redis/内存双实现）——AI 回复先 push，客户端 ack 后 drain；重连后 `resume` 拉取未确认消息补发。

> **降级说明**：Windows 环境 PostgresSaver 不可用时（见 6.6），状态不写 checkpoint，改由 `session_store.save_round` 每轮把 messages_json 落库、重连时 `get_session_state` 重建 history——断线续谈退化为"按已落库对话重建"（无回放保留）。

### 5.4 报告生成链路
```
end_negotiation → compute_simple_result（即时）→ end_session 落库
  → _submit_report_generation
      ├─ 生产：Celery delay → worker 生成 → 事件总线 publish → API 进程 → WS report_ready
      └─ dev/broker 不可用：同步生成 → 先落库通知 → 再 WS 推送
  → 通知落库（notifications 表）+ WS 实时推送（双写，防断连丢通知）
```

### 5.5 支付链路
```
前端 PaymentView → POST /api/payment/orders {type: subscribe|scenario}
  → create_order（事务）→ build_pay_url（支付宝 RSA2 签名）→ 返回 pay_url
  → 用户跳转支付宝 / 一键直付（mock trade_no 前缀跳过验签）
  → 支付宝异步回调 POST /api/payment/notify
      → RSA2 验签 → 金额校验 → 幂等（payment_log UNIQUE）→ 更新订单 + 用户角色
      → 发布事件 → WS 推送"支付成功"通知
  → 前端 GET /orders/{id} 轮询订单状态
```

### 5.6 自定义场景（PRD 未来项提前落地）
- 用户创建场景：title/rules/对手人设/开场白/安全话术/维度（key/label/direction/first_offer/bottom_line/keywords）+ weights（覆盖全维度且和≈1）
- 校验器严格校验（422 SCENARIO_INVALID）；私有可见（他人 404/403）；级联删除
- 引擎加载：`load_scenario_for_session` DB 优先（自定义）→ 官方回退 JSON 文件

---

## 6. 关键设计决策与难点攻坚（面试亮点）

### 6.1 战术系统：规则引擎优先，LLM 兜底
- **决策**：8 种战术（好 cop/bad cop、时间压力、最后通牒、假底线、分而治之、沉默施压、让步诱饵、信息不对称）用 Python 优先级决策表实现，规则不命中才调 LLM。
- **理由**：谈判战术判定是确定性逻辑（意图+阶段+历史），规则引擎毫秒级、零成本、可单测；LLM 兜底覆盖长尾。
- **效果**：战术命中统计成为复盘与管理后台 KPI。

### 6.2 底线约束：永不突破 + 可解释评分
- 话术生成后**数值提取**（LLM 结构化 JSON + 正则兜底 + 中文数字"两百万"），与场景各维度底线比对（direction=min 不允许低于底线、max 不允许高于上限）。
- 突破 → 重试 ≤3 次（携带 retry_hint 让 LLM 调整）→ 仍突破 → `fallback_node` 发安全话术。
- 检查对象是 **AI 生成的回复**（约束 AI 让步），同时用户报价与 AI 底线的贴近度作为客观分依据——**可解释、可测试**（引擎单测覆盖重试路径）。

### 6.3 双轨评分：客观规则 + 主观 LLM Judge
- 客观分：让步幅度/底线贴近/战术命中/时长 → 确定性规则，可复现。
- 主观分：LLM Judge 从谈判技巧、信息获取、情绪管理等维度打分。
- 合成：`total = 0.6×客观 + 0.4×主观归一化`——兼顾可解释性与模型判断力。

### 6.4 并发与成本控制（生产级细节）
- **Redis 分布式锁**（SET NX EX 10）：防同一 session 并发 invoke → 429。
- **LLM 令牌桶限流**（Lua）：5 次/分钟/用户 → 防打爆成本。
- **轻模型分流**：意图提取/教练用轻模型（light=True），话术生成用主力模型。
- **Reranker 单例缓存**：首次加载 12s → 缓存后即时。

### 6.5 事件总线：worker 无 WS 通道的桥接
- Celery worker 无法直推 WebSocket → Redis pub/sub：worker 发布通知事件 → API 进程监听 → `ws_manager.send_to_user` 推送。
- 支付成功、报告完成两条链路均接入；发布失败静默（通知仍落库，客户端可拉取）。

### 6.6 Windows 平台 PostgresSaver 兼容（troubleshooting #52）
- **现象**：`Psycopg cannot use the 'ProactorEventLoop'`，PostgresSaver 每次降级。
- **深挖**：uvicorn 0.36+ `asyncio_loop_factory` 在 Windows 硬编码 ProactorEventLoop，完全绕过 policy 设置。
- **方案演进**：先写 run.py 手动 Selector loop 驱动 uvicorn Server → 发现 psycopg async 在 Selector loop 下**挂起而非报错** → 回退标准 uvicorn + `open_checkpointer` 8s 超时快速降级（checkpointer 置 None，状态改走 messages_json 落库重建）。
- **结论**：Windows 开发机放弃 PostgresSaver、走降级路径保证全功能可用；**生产 Linux 环境天然支持**（8s 超时只在连接建立时探测一次，不影响每轮谈判延迟）。
- **面试加分**：能讲清楚"为什么不在 Windows 上强行修"——降级路径保证全功能可用，生产 Linux 环境天然支持 PostgresSaver。

### 6.7 鉴权与安全
- JWT 双 token（access 24h / refresh 7d）+ bcrypt 12 rounds。
- 资源归属校验全覆盖：报告/会话/对比/通知/自定义场景，越权 403/404。
- 登录失败 5 次 Redis 锁定 15 分钟；封禁账号 423。
- 支付回调：RSA2 验签 + 金额校验 + 幂等 + 主动对账（Celery beat）。
- 管理后台防自改（不能改自己角色/管理员位）。

### 6.8 可观测性
- LangFuse：LLM 调用全链路追踪（token 数/延迟/成本）。
- 管理后台实时指标：在线连接数/战术命中分布/运营 KPI。
- 审计日志：所有管理操作写 admin_audit_log。

---

## 7. 测试体系与工程质量

### 7.1 测试分层
| 层 | 数量 | 覆盖 |
|---|---|---|
| 后端单元/集成（pytest） | 477 passed + 2 skipped | 引擎 85 / 支付通知 91 / 认证 56 / 管理+LLM+RAG 70 / 报告 43 / 基础设施 95 / 场景会话 52 |
| 前端组件（vitest） | 21 | api 层/store/Login/Register/Admin |
| E2E（Playwright） | 4 | 注册登录/登录失败/忘记密码/发起谈判 |
| CI 守卫 | — | ruff lint / alembic check（迁移漂移）/ 部署资产存在性 |

### 7.2 测试方法论
- **测试先行（TDD）**：逻辑实现前先写失败测试，如引擎底线重试、支付幂等、WS 协议。
- **MockLLM 全功能可测**：无 LLM 密钥时引擎自动降级 MockLLM，CI 无需真实模型。
- **真实数据库演练**：迁移对空库跑 + `alembic check` 防漂移；测试用独立库自动建删表。

### 7.3 工程资产
- `docs/troubleshooting.md`：54 条问题-根因-解决方案记录（面试可引用："我遇到的每一个问题都沉淀成文档"）。
- `docs/negotiation-agent-prd.md`：PRD v3.0 + 附录 C 功能清单与测试基线。
- Alembic 7 个迁移版本链。

---

## 8. 高频面试题速答（Q&A）

### Q1：为什么用 LangGraph 而不是直接循环调用 LLM？
谈判是**有状态、多阶段、需要分支决策**的流程（意图→战术→话术→底线→回退），LangGraph 把流程建模为显式节点图，每个节点是纯函数可单测，图可序列化到 PostgresSaver 实现断点续谈，还支持条件边（如底线检查失败重试）。直接循环写的话，状态管理和分支逻辑会散落在代码里，且没有标准化的 checkpoint 机制。

### Q2：AI 对手如何保证不突破底线？
三层保障：① 话术生成 prompt 携带场景维度底线与方向约束（min/max）；② 生成后数值提取器做**确定性校验**（正则为主、LLM 结构化兜底），把 AI 回复中的数值与各维度底线比对，突破即触发重试（≤3 次，携带修正提示）；③ 重试仍失败则回退安全话术（fallback 节点）。因为校验是纯规则而非依赖模型自觉，所以是可测试、可证明的。

### Q2b：RAG 记忆和 messages_json 历史是什么关系？会不会重复？
不冲突，用途不同：`messages_json` 是**完整逐轮对话**，用于回放、报告与断线后重建上下文，每轮追加（偶数下标=用户、奇数下标=AI）；Milvus 向量记忆是**相似历史片段检索**，解决长对话时全量 history 超出 LLM 上下文窗口的问题——把最相关的 3 条历史注入话术生成 prompt，让 AI 记得关键承诺而不必塞入全部文本。

### Q3：WebSocket 断线了怎么办？
两层：PostgresSaver 每轮落盘图状态，重连按 thread_id 恢复完整状态；AI 回复先进缓冲队列，客户端 ack 才删，重连后 resume 补发。前端配指数退避自动重连。Windows 降级环境下（PostgresSaver 不可用）则从 messages_json 重建历史（见 5.3 降级说明）。

### Q4：流式输出怎么做的？为什么是真流式？
BaseLLM 抽象 `astream()`，utterance 节点边生成边回调 `stream_callback`，路由层把分片通过 `ws.send_json({type:"token"})` 转发。重试轮次自动退回非流式（全量一次性发）以简化异常路径。MockLLM 模拟流式分片，保证测试可验证。

### Q4b：ws_buffer 的 ack/resume 会不会导致消息重复或丢失？
消息先 push 后 ack（客户端确认收到才删除），所以不会丢；可能的重复由前端去重（按会话内序号/消息内容比对）。缓冲键含 session_id，断线期间消息全部保留在 Redis，resume 一次性补发。多 worker 场景下用 Redis 实现保证跨进程共享（内存实现仅单进程 dev 用）。

### Q5：为什么 embedding 用 bge-small-zh 而不是 BGE-M3？
性能预算。CPU 上 BGE-M3 单条 9 秒，远超 PRD 的 200ms 预算；bge-small-zh 实测 15ms，512 维。维度变化时 RAG 自动 drop 重建 collection（旧数据弃），并保留 BGE-M3 选项供生产 GPU 环境。

### Q6：Celery worker 怎么把报告完成推给用户的？
worker 进程无法直连用户 WS。用 Redis pub/sub 事件总线：worker 发布 `report_ready` 事件 → API 进程监听 → ws_manager 按 user_id 找到连接推送。若推送失败（用户已断线）通知仍落库，客户端下次拉取可见（双写设计）。单 API 实例场景无重复推送问题；多实例部署时推送只发生在持有该用户连接的实例上（ws_manager 按实例注册）。

### Q7：支付回调怎么保证安全和幂等？
RSA2 验签防伪造 → 金额与订单比对 → payment_log 唯一约束（out_trade_no+trade_no）防重复回调 → 事务更新订单与用户权限 → Celery beat 定时主动对账兜底漏单。mock 直付仅当回调**不携带 sign** 且 trade_no 以 `mock_` 前缀开头时跳过验签，且仍需通过建单归属与金额校验，生产正式环境配置真实公钥后该路径不生效（支付宝回调必带签名）。

### Q7b：报告侧为什么没有像支付侧那样的轮询兜底？
支付是第三方交互、回调时序完全不可控，所以做了主动轮询对账；报告是本系统内部任务，完成事件有双重保障（事件总线推送 + notifications 落库可拉取），用户在报告列表页/个人中心都能拉到结果，无需轮询。

### Q8：并发情况下怎么防同一会话重复调用 LLM？
Redis SET NX 分布式锁（10s 过期），同一 session_id 上一条未完成则 429 拒绝；同时 LLM 令牌桶限流（5 次/分钟/用户）控制整体成本。

### Q9：这个项目怎么测试 LLM 相关逻辑？
核心思路是**抽象 + 降级**：BaseLLM 接口，MockLLM 实现确定性行为，引擎单测全部走 Mock；真实 LLM 链路由 CI 的 smoke 脚本（配置密钥时跑真实 ainvoke/astream）覆盖。数值提取用"LLM 结构化 + 正则兜底"双通道，正则部分纯规则可单测。

### Q10：如果让你重新做，会改什么？
① 引擎节点再多加"信息探询"阶段，让对手主动获取用户信息（当前对手偏被动）；② 多场景并行的"对抗式训练"数据采集，用真实用户谈判数据微调战术选择；③ 支付模块接入真实正式环境（当前沙箱网关外部故障）；④ 前端谈判室迁移到 WebRTC 语音交互（远期）。

### Q11：为什么报告要双轨评分？
纯客观规则可解释但偏机械（可能漏掉"这轮话说得漂亮"）；纯 LLM 主观分不可复现且贵。双轨合成兼顾解释性与判断力，且两轨数据各自沉淀（曲线/维度），支撑趋势与对比功能。合成公式：`total = 0.6×客观 + 0.4×主观`，主观分由 LLM Judge 按客观分同量纲输出（0-100 归一），judge 调用固定 temperature 保证同会话重生成分数稳定。

### Q12：自定义场景的维度校验为什么这么严格？
谈判引擎的底线检查和评分都依赖结构化维度（key/label/direction/数值/关键词），weights 必须覆盖全部维度且和≈1，否则引擎跑起来会行为异常。宁可创建时 422 拒绝，也不让坏数据进引擎。

---

## 附录 A：讲解演示路径（跑通全流程的快捷清单）

```powershell
# 1. 基础设施
docker compose up -d postgres redis
# 2. 后端（.venv）
cd backend; .\.venv\Scripts\python run.py        # :8765
# 3. 前端
cd frontend; npm run dev                          # :5173
# 4. 演示顺序
#    注册新账号 → 大厅选择"薪资谈判" → 谈判室对话 2-3 轮（看右屏战术/分数实时变化）
#    → 教练建议 → 结束谈判 → 即时结果 → 报告详情（双轨曲线/PDF）
#    → 个人中心（趋势/通知/改密） → 管理后台(/admin, is_admin)
#    → 一键直付（支付页, 秒成功）→ 角色升级 pro → 通知实时推送
# 备注：本地演示库已有账号 3137504285@qq.com / mt123456（free+admin，仅本地演示库，请勿外传）
```

## 附录 B：数据速查
- 后端测试：477 passed + 2 skipped；ruff clean
- 前端：vitest 21 + Playwright E2E 4 + build 通过
- 迁移链：53f0702dbf0f → 58f71c3926e5 → 8884346523fb → b9239a8602ae → 360f036d2731 → 6c8e2dfd61ee → 6a5e73674b6a
- 服务：后端 8765 / 前端 5173 / Postgres 5433 / Redis 6379
- 已知限制：支付宝沙箱网关外部 502；Windows 下 PostgresSaver 降级 JSON（生产 Linux 正常）
