# 谋谈（MouTalk）项目完成进度总览

> 依据 `docs/negotiation-agent-prd.md`（v3.0 终版）结构整理，实时反映实现进度。
> 状态图例：✅ 已完成 · ⚠️ 部分完成/外部阻塞 · 📋 待办/规划中
> 最后更新：2026-08-06

---

## 0. 总体状态

| 维度 | 状态 | 说明 |
|---|---|---|
| 用户故事 5 项 | ✅ 4 项完成 | 故事 5（支付）代码完成，沙箱网关外部故障 |
| 核心功能 8 项 | ✅ 7 项完成 | 功能 8（支付）同故事 5 |
| 实现难点 9.1-9.14 | ✅ 14 项全部落地 | 全部实现（含新增工程能力）|
| 后端测试 | ✅ 339 passed | 42 个测试文件，ruff clean |
| 基础设施 | ✅ 运行中 | Postgres/Redis/Milvus/Celery 全部健康 |
| 前端 | ✅ 可访问 | Vite dev 5173 + 生产构建通过 |

---

## 1. 用户故事进度

### 故事 1：用户注册与登录 ✅
| 验收标准 | 状态 | 实现位置 |
|---|---|---|
| 邮箱+密码注册登录 | ✅ | `backend/app/api/auth.py` |
| 注册需邮箱验证 | ✅ | 6 位验证码（SMTP QQ 邮箱；dev 降级打印）|
| JWT 鉴权，过期自动刷新 | ✅ | access 24h + refresh 7d |
| 登录后可看个人信息和谈判历史 | ✅ | `/auth/me` + `/sessions` + `/reports` |
| 密码错误 5 次锁定 | ✅ | Redis `login_fail:{email}` 锁 15 分钟 |

### 故事 2：发起一场谈判 ✅
| 验收标准 | 状态 | 实现位置 |
|---|---|---|
| 展示 3 个场景包 | ✅ | `backend/app/scenarios/*.json` |
| 简介/难度/对手风格 | ✅ | 前端 LobbyView 卡片 |
| 分屏式谈判室 | ✅ | `frontend/src/views/RoomView.vue` |
| 谈判背景和规则说明 | ✅ | briefing/rules + 合规声明 |

### 故事 3：进行多轮谈判对话 ✅
| 验收标准 | 状态 | 实现位置 |
|---|---|---|
| 气泡对话分列两侧 | ✅ | RoomView 左屏 |
| 右屏实时分数/曲线/底线/战术 | ✅ | ECharts + meta 推送 |
| 8 种战术动态出招 | ✅ | `backend/app/engine/tactics.py` 规则引擎 |
| 无轮次上限 / 随时结束 | ✅ | WS 循环 + end_negotiation |
| 流式输出（WebSocket）| ✅ | 伪流式分片（真流式 Phase 2）|
| 不突破底线约束 | ✅ | 底线检查 + 重试 3 次 + 安全话术 |

### 故事 4：查看复盘报告 ✅
| 验收标准 | 状态 | 实现位置 |
|---|---|---|
| 简版结果即时显示 | ✅ | `report_service.compute_simple_result` |
| 详细报告异步生成+通知 | ✅ | Celery + WS `report_ready`（dev 同步降级）|
| 双轨维度/曲线/弱点/建议 | ✅ | `reports` 表 + 详情页 |
| 历史报告回顾和对比 | ✅ | 列表 + **对比页**（新增）|
| 报告下载 PDF | ✅ | matplotlib + reportlab（后端+前端）|

### 故事 5：订阅与支付 ⚠️
| 验收标准 | 状态 | 说明 |
|---|---|---|
| 免费层 5 次/月/场景 | ✅ | Redis Lua 原子计数 |
| Pro 订阅 / 场景包单买 | ✅ | orders + user_scenario_access |
| 支付宝沙箱支付 | ⚠️ | **代码完成**（真实 RSA2 签名链接已验证生成）；沙箱网关 502 外部故障，watchdog 探测中 |
| 支付完成即时更新权限 | ✅ | 回调验签+幂等+主动对账 |

---

## 2. 核心功能进度

| 功能 | 状态 | 说明 |
|---|---|---|
| 1 谈判引擎（5 节点状态机）| ✅ | 意图→战术→话术→底线→回退，LangGraph |
| 2 分屏谈判室 | ✅ | 前端完整（气泡/看板/曲线/战术灯）|
| 3 双轨复盘系统 | ✅ | 客观分规则 + 主观分 LLM Judge |
| 4 场景包系统 | ✅ | 3 JSON 包 + 可扩展 |
| 5 战术系统 | ✅ | 8 战术 + deadlock_break + neutral |
| 6 向量记忆系统 | ✅ | Milvus + BGE embedding + **Reranker** |
| 7 用户与权限系统 | ✅ | JWT + 三级权限 + 额度 |
| 8 支付系统 | ⚠️ | 同故事 5（沙箱网关外部阻塞）|

---

## 3. 技术流程进度

| 流程 | 状态 | 说明 |
|---|---|---|
| 8.1 一次谈判循环时序 | ✅ | WS → LangGraph → LLM → Milvus → Postgres 全链路 |
| 8.2 WebSocket 流式输出 | ✅ | 伪流式 + 心跳 + **断线重连缓冲**（新增）|
| 8.3 向量记忆 RAG 流程 | ✅ | BGE embed → Milvus top-10 → **Reranker 重排** → top-3 注入 |
| 8.4 异步复盘生成 | ✅ | Celery（dev 同步降级）+ report_ready 推送 |
| 8.5 支付回调 | ✅ | 验签/幂等/事务/对账 beat 全实现（网关外部阻塞）|

---

## 4. 技术约束达成情况

### 性能（PRD 9.2 预算 vs 实测）
| 指标 | PRD 目标 | 实测 | 状态 |
|---|---|---|---|
| 底线检查节点 | <100ms | 纯规则毫秒级 | ✅ |
| 单轮推理全链路 | <5s | GLM 真实调用 2-5s（网络波动）| ✅ |
| Embedding 单次 | <200ms | bge-small-zh **15ms** | ✅ |
| 复盘报告生成 | <30s | 同步路径 1-2s（LLM Judge 5-15s）| ✅ |
| WebSocket 首屏 | <2s | 伪流式分片即时 | ✅ |

### 安全
| 项 | 状态 | 说明 |
|---|---|---|
| JWT 鉴权 + 刷新 | ✅ | 双 token 类型校验 |
| bcrypt 密码哈希 | ✅ | 12 rounds |
| 数据隔离 | ✅ | 所有资源归属校验（报告/会话/对比）|
| 支付回调安全 | ✅ | 验签 + 金额校验 + 幂等 |
| **并发锁（9.13 新增）** | ✅ | Redis SET NX，429 防并发 |
| **LLM 限流（9.6 新增）** | ✅ | 5 次/分钟/用户令牌桶 |
| 密钥管理 | ✅ | 全部 .env（gitignore）|
| LangFuse 可观测 | ✅ | 云端上报已验证 |

---

## 5. 实现难点 9.1-9.14 进度

| # | 难点 | 状态 | 落地说明 |
|---|---|---|---|
| 9.1 断点续谈 | ✅ | PostgresSaver + **Redis 断线缓冲队列**（新增 ack/resume/replay 协议）|
| 9.2 Milvus+BGE 部署 | ✅ | Milvus 完整版 Docker；embedding 抽象层（维度自适应）|
| 9.3 数值提取 | ✅ | LLM 结构化 + 正则兜底 + 中文数字 |
| 9.4 流式桥接 | ✅ | 伪流式 MVP（真流式 Phase 2 待办）|
| 9.5 战术跨轮 | ✅ | tactic_context 状态字段 |
| 9.6 成本控制 | ✅ | 轻模型 + **令牌桶限流** + LangFuse 告警 |
| 9.7 战术规则引擎 | ✅ | Python 优先级决策表 |
| 9.8 连接管理 | ✅ | **WsConnectionManager + 优雅关闭**（新增）|
| 9.9 主客观对齐 | ✅ | total = 0.6×客观 + 0.4×主观归一化 |
| 9.10 PDF 导出 | ✅ | matplotlib + reportlab + 前端下载 |
| 9.11 免费额度并发 | ✅ | Redis Lua 原子 |
| 9.12 支付幂等 | ✅ | payment_log UNIQUE + 验签 + 对账 |
| 9.13 并发锁 | ✅ | Redis SET NX EX 10 + 429 |
| 9.14 合规 | ✅ | 背景页声明 + 模拟信息标注 |

---

## 6. 技术栈落地清单

| 层 | PRD 规划 | 实际落地 | 状态 |
|---|---|---|---|
| 前端 | Vue3+Vite+ElementPlus+Pinia+ECharts | 同左，全部使用 | ✅ |
| 后端 | FastAPI+LangGraph+Celery+Redis+JWT | 同左 + 伪流式 | ✅ |
| 数据 | PostgreSQL+Milvus+BGE-M3+BGE-Reranker | Postgres + **Milvus 3.0 完整版** + **bge-small-zh**（15ms）+ **bge-reranker-base** | ✅（模型有调整）|
| 模型 | GLM-4-Plus + DeepSeek V4 Pro | **deepseek-v4-flash**（opencode 网关，主/轻量全用）| ✅ |
| 可观测 | LangFuse 自部署 | **LangFuse Cloud**（Basic Auth 已验证）| ✅ |
| 支付 | 支付宝沙箱/正式 | 沙箱代码完成，**网关外部阻塞** | ⚠️ |
| 部署 | Docker + GitHub Actions | Docker Compose 全服务 + **CI 已配置** | ✅ |

### 关键技术调整（相对 PRD）
| 项 | 原案 | 实际 | 原因 |
|---|---|---|---|
| 默认 embedding | BGE-M3（1024 维）| bge-small-zh（512 维，15ms）| CPU 上 BGE-M3 9s/条远超预算；BGE-M3 仍可选 |
| LLM 网关 | 智谱直连 | opencode.go 网关 | 统一网关（deepseek-v4-flash，主/轻量同模型）|
| RAG 架构 | — | 官方 SDK 裸管线（非 LangChain/LlamaIndex）| 业务定制控制力 |

---

## 7. 新增工程能力（PRD 之外）

| 能力 | 说明 |
|---|---|
| 断线重连缓冲队列 | WS ack/resume/replay + Redis 缓冲 + 指数退避重连 |
| BGE-Reranker 重排 | Milvus top-10 → 精排 → top-3 |
| Redis 并发锁 | 429 防同 session 并发 |
| LLM 令牌桶限流 | 5 次/分钟/用户 |
| 连接管理+优雅关闭 | shutdown 广播 server_shutdown |
| 报告对比页 | 总分条形/曲线叠加/维度对比表 |
| 前端 PDF 下载 | blob + 轮询重试 |
| Celery Worker 镜像化 | host.docker.internal 连本机 Redis |

---

## 8. 已知问题与阻塞

| # | 问题 | 影响 | 状态 |
|---|---|---|---|
| 1 | 支付宝沙箱网关 502（支付宝侧）| 沙箱支付端到端无法完成 | ⏳ 外部等待，watchdog 每 10 分钟探测 |
| 2 | BGE-M3 CPU 9s/条 | 仅 BGE-M3 选项慢 | ✅ 已用小模型规避；生产建议 xinference |
| 3 | 真流式未实现 | 首 token 延迟略高 | 📋 Phase 2 |
| 4 | Reranker 首次加载 12s | 仅首次 | ✅ 单例缓存 |
| 5 | Celery 需 Docker | Windows 无法直跑 | ✅ compose 已就绪 + dev 降级 |

---

## 9. 测试覆盖

| 测试文件 | 覆盖 | 用例数 |
|---|---|---|
| test_negotiation_ws.py | WS 鉴权/轮次/收尾 | ~15 |
| test_negotiation_ws_buffer.py | 断线缓冲/回放/锁 429 | 4 |
| test_negotiation_lock.py | 并发锁 | 5 |
| test_llm_rate_limit.py | 令牌桶限流 | 4 |
| test_ws_manager.py | 连接管理 | 4 |
| test_embeddings.py | hash/BGE/降级 | 8 |
| test_rag*.py | RAG 存取/检索/重排/注入 | ~17 |
| test_reranker.py | 重排（含真实模型）| 5 |
| test_report*.py | 报告/对比/PDF | ~20 |
| test_alipay*.py | 支付签名/验签/查询 | ~30 |
| test_auth.py | 认证/锁定/刷新 | ~20 |
| 其他 | 引擎/战术/提取/额度/场景 | 剩余 |
| **合计** | **339 passed** | 42 个文件 |

---

## 10. 服务运行状态（当前）

```
后端 uvicorn      8765  ✅ 运行中（GLM 真实推理）
前端 Vite         5173  ✅ 运行中（代理指向 8765）
Celery Worker     Docker ✅ 运行中（连本机 Redis）
Milvus 三容器     19530 ✅ 全部 healthy
Postgres          5433  ✅ healthy
Redis             6379  ✅ 运行中
支付宝 watchdog   --    ✅ 监控沙箱恢复
```

---

*依据 PRD v3.0 结构整理。详细实现说明见 `docs/negotiation-agent-prd.md` 附录 B；问题排查见 `docs/troubleshooting.md`。*

---

# ���£�PRD v4.0 �׶� 1.5 ������ǿ��2026-08-07 ��ɣ�

| # | ��ǿ�� | ״̬ | ˵�� |
|---|---|---|---|
| 1 | �������ߣ�9.18��| ? | /api/reports/trends �¾ۺϣ���ѽ� 3 ��/Pro ���� |
| 2 | ����֪ͨ��9.15��| ? | notifications �� + ˫д + δ��/�Ѷ�/30 ������ |
| 3 | �������ģ����� 6��| ? | /api/quota/me + ProfileView�����/֪ͨ/���ģ�|
| 4 | ̸�лطţ�9.17��| ? | /api/sessions/{id}/replay + ReplayTimeline�����٣�|
| 5 | ������̨��9.16��| ? | /api/admin/* ���ӿ� + is_admin ��Ȩ + ��Ʊ� |
| 6 | Э��/��˽ҳ������ 8��| ? | TermsView ˫ҳ + ע��ض���ѡ |
| 7 | HTTPS ����9.19��| ? | Caddy + docker-compose.prod.yml + .env.prod.example |
| 8 | ���ݱ��ݣ�9.20��| ? | scripts/backup.sh + �������� |

**����**��367 passed��+28��+ ruff clean + alembic check ��Ư��
**�˵���**��quota/trends/notifications��˫д��⣩/replay/admin��403��200��ȫͨ
**����**��tactic-stats �ۺ����� history �־û� tactic �ֶΣ���ǰΪ�գ��� troubleshooting #40��
