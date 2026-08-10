# AGENTS.md — 谋谈 (MouTalk) 项目约定

多轮深度谈判模拟 Agent。技术栈：Vue 3 + FastAPI + LangGraph + 智谱 GLM + Celery + Milvus。需求文档：`docs/negotiation-agent-prd.md`（v3.0 终版）。

## 核心约定（必须遵守）

**每次开始动手（写代码/改文件）之前，必须先调用 skill 工具加载对应工作流，不得仅凭自身能力直接制作。**

任务 → skill 映射：

| 任务 | 先加载的 skill |
|---|---|
| SQLAlchemy 数据建模 / 数据库集成 | source-driven-development |
| 认证 / JWT / 支付 / 权限 | security-and-hardening |
| API 路由 / WebSocket 协议 / 模块边界 | api-and-interface-design |
| 复盘报告 / 业务逻辑 | test-cases + test-driven-development |
| 任何逻辑实现 / bug 修复 | test-driven-development（先写测试） |
| 前端 UI / 组件 / 页面 | frontend-design |
| 性能优化 / 流式响应 | performance-optimization |
| LangFuse / 日志 / 埋点 | observability-and-instrumentation |
| CI/CD / Docker 部署 | ci-cd-and-automation |
| 提交 / 分支管理 | git-workflow-and-versioning |
| 新功能规划 / 需求澄清 | spec-driven-development + interview-me |
| 环境疑难 / 测试失败排查 | debugging-and-error-recovery |

原则：测试先行（TDD）、小步增量交付、以 PRD 为准、不擅自扩大范围。

## 问题记录约定（必须遵守）

**遇到的每一个问题（bug / 报错 / 环境疑难 / 测试失败），排查解决后必须追加记录到 `docs/troubleshooting.md`**（问题 / 根因 / 解决方案，编号递增，参考已有条目格式）。修复代码之前或之后记录均可，但不得跳过。

## 常用命令

```powershell
# 环境（Windows，venv 在 backend/.venv）
cd backend
.\.venv\Scripts\python -m pytest tests -q      # 运行测试（当前 270 个）
.\.venv\Scripts\python -m ruff check app tests alembic # lint
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000  # 启动后端

# 数据库迁移（Alembic；改模型后必须生成迁移，CI 有 alembic check 守卫）
$env:MOUTALK_TEST_DB_URL = "postgresql+psycopg://moutalk:moutalk_dev_pw@localhost:5433/moutalk_migtest"
.\.venv\Scripts\python -m alembic revision --autogenerate -m "描述"   # 生成迁移（对空库 moutalk_migtest 跑）
.\.venv\Scripts\python -m alembic upgrade head                        # 应用迁移
.\.venv\Scripts\python -m alembic check                               # 校验模型与迁移无漂移

# 基础设施（项目根目录）
docker compose up -d postgres redis
```

## 环境注意事项

- **Windows 开发机**：Celery 需走 Docker；Milvus 用 Lite（本地 `milvus.db` 文件）。
- **Redis**：本机已有 Redis 占 6379（直接用）；Docker 容器映射 6380。
- **LLM**：`LLM_API_KEY` 未配置时引擎自动降级 MockLLM（全功能可测）；配置后自动切 GLM。密钥只放 `.env`（已 gitignore），禁止写入代码或提交仓库。
- **数据库**：Postgres 16（moutalk/moutalk_dev_pw，db: moutalk），Docker 映射 **5433**（本机另有 PostgreSQL 15 服务占用 5432，勿改端口）。测试用独立库 `moutalk_test`（自动创建/建表/删表）。
- 生产环境约束：Milvus 完整版、PostgresSaver、真流式，见 PRD 第 9 节。

## 项目结构速览

```
backend/app/
├── engine/     # 谈判引擎（state/nodes/tactics/extractor/llm/engine）
├── scenarios/  # 场景包 JSON（it_procurement / salary / supplier）
├── core/       # 配置（config.py）+ 数据库（db.py: engine/SessionLocal/Base/get_db）
├── models/     # SQLAlchemy 模型（user/scenario/session/report/payment）
├── services/   # 业务服务（session_store 会话持久化 / scenario_seed 场景入库 / auth 认证 / security 哈希+JWT）
├── api/        # 路由（auth 认证 / scenarios 场景包 / sessions 会话+额度 / negotiation WebSocket / reports 复盘报告 / payment 支付）
└── main.py     # FastAPI 入口（统一错误格式 + 启动建表 + 场景种子）
backend/tests/  # pytest（270 个测试）
```
