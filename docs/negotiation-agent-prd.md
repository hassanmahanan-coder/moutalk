

# 谋谈（moutalk）

## Product Requirements Document: 多轮深度谈判模拟 Agent

**版本**: 4.0（增强版）
**日期**: 2026-08-06
**作者**: One day (Product Owner)
**质量评分**: 97/100

---

## 执行摘要

多轮深度谈判模拟 Agent 是一套基于多 Agent 协作架构的谈判训练系统。用户可在分屏式 Web 界面中与 AI 对手进行不设上限轮次的模拟谈判，结束后获得双轨评估报告。系统内置 3 个行业场景包（IT 采购、薪资谈判、供应商压价）、8 种进攻型战术，面向企业销售/采购培训和职场个人用户。

采用 SaaS 订阅 + 场景包商店模式盈利。技术栈基于 Vue 3 + FastAPI + LangGraph + 智谱 GLM + Celery + Milvus，单机可支撑 50 人以下并发。

本 PRD 在 v3.0 终版基础上，结合 v3.1 实施追踪（附录 B）的落地反馈，补充个人中心、离线通知、合规协议、管理后台、谈判回放、战术监控、进步曲线、HTTPS 部署、数据备份等增强功能，形成覆盖生产上线全要求的 v4.0 增强版。

---

## 问题陈述

**现状**: 谈判能力提升依赖真人演练（成本高、场景少、无法重复）或读书/看课（缺乏实战感）。企业培训中模拟谈判的组织成本高，个人用户缺乏低成本的练习渠道。

**解决方案**: 基于多 Agent 协作的 Deep Agent 系统，让用户随时与 AI 对手进行无限轮次模拟谈判，谈判后获得包含客观分和主观分在内的完整复盘报告。

**商业价值**: 面向企业培训部门（年费 5-20 万）和个人用户（月费 49-99 元），附加场景包商店（99-299 元/包）增值收入。

---

## 成功指标

**核心 KPI:**
- **月完成谈判次数** ≥ 1000 次（上线首月目标）
- **付费转化率** ≥ 5%（免费用户 → Pro 订阅）
- **次月留存率** ≥ 30%

**验证方式**: LangFuse + PostgreSQL 统计数据，Web 端内嵌事件埋点。

---

## 用户画像

### 主要：企业销售/采购人员
- **角色**: B2B 销售经理、采购总监
- **目标**: 在无风险环境中练习复杂谈判，准备重要客户会面
- **痛点**: 真实谈判搞砸代价大，同事陪练时间成本高
- **技术等级**: 中级

### 次要：职场个人用户
- **角色**: 求职者（练薪资谈判）、创业者（练融资谈判）
- **目标**: 提升个人谈判能力，获得客观的进步反馈
- **痛点**: 缺乏练习对象和评估标准
- **技术等级**: 初级

---

## 用户故事与验收标准

### 故事 1：用户注册与登录

**作为一个** 访客
**我想要** 注册账号并登录系统
**以便** 使用谈判模拟功能

**验收标准:**
- [ ] 支持邮箱+密码注册和登录
- [ ] 注册需邮箱验证
- [ ] JWT Token 鉴权，过期自动刷新
- [ ] 登录后可查看个人信息和谈判历史
- [ ] 密码错误 5 次后临时锁定账号

### 故事 2：发起一场谈判

**作为一个** 已登录用户
**我想要** 选择一个场景包开始谈判
**以便** 与 AI 对手进行模拟练习

**验收标准:**
- [ ] 展示可用场景包列表（IT 采购、薪资谈判、供应商压价）
- [ ] 每个场景包显示简介、难度标签、对手风格
- [ ] 选择后进入分屏式谈判室
- [ ] 系统展示谈判背景和规则说明后开始

### 故事 3：进行多轮谈判对话

**作为一个** 谈判中的用户
**我想要** 在分屏界面中与 AI 对手对话
**以便** 完成完整的谈判流程

**验收标准:**
- [ ] 左屏：气泡对话界面，用户和对手消息分列两侧
- [ ] 右屏：实时显示当前分数、让步曲线、底线状态、战术提示
- [ ] 对手基于 8 种战术（红脸白脸、时间压迫、最后通牒、虚假底线、分而治之、沉默施压、让步诱饵、信息不对称）动态出招
- [ ] 对话不设轮次上限，用户可随时点击"结束谈判"
- [ ] 对手回复采用流式输出（WebSocket）
- [ ] 对手回复不会突破场景包配置的底线约束

### 故事 4：查看复盘报告

**作为一个** 完成谈判的用户
**我想要** 查看完整的复盘评估报告
**以便** 了解自己的谈判表现和改进方向

**验收标准:**
- [ ] 谈判结束后先显示简版结果（得分 + 胜负判定）
- [ ] 详细报告后台异步生成，生成后通知用户（WebSocket/轮询）
- [ ] 报告包含：总分、各维度得分（客观分+主观分）、让步曲线图、薄弱环节识别、改进建议
- [ ] 历史报告可回顾和对比
- [ ] 报告支持下载为 PDF

### 故事 5：订阅与支付

**作为一个** 免费用户
**我想要** 升级为 Pro 订阅或购买场景包
**以便** 解锁更多功能

**验收标准:**
- [ ] 免费层：所有场景各5次/月
- [ ] Pro 订阅：无限次数，可查看完整复盘报告
- [ ] 场景包单买：99-299 元/包
- [ ] 接入支付宝沙箱支付（开发环境）
- [ ] 支付完成后即时更新用户权限

### 故事 6：个人中心与订阅管理

**作为一个** 已登录用户
**我想要** 在个人中心查看账号信息、订阅状态与额度使用
**以便** 集中管理我的账户与训练进度

**验收标准:**
- [ ] 展示用户邮箱、角色（免费/Pro/企业）、订阅到期时间
- [ ] 展示本月各场景免费额度使用情况（已用/剩余）
- [ ] 展示谈判历史入口（跳转复盘报告列表）
- [ ] 支持退出登录
- [ ] Pro 用户展示续费入口，到期前 7 天提示

### 故事 7：离线通知与消息中心

**作为一个** 用户
**我想要** 在离线时不丢失系统通知（如报告生成完成、支付成功）
**以便** 下次登录能补看重要消息

**验收标准:**
- [ ] 报告异步生成完成时，若用户在线则 WS 推送，离线则写入 notifications 表
- [ ] 支付成功权限更新时，同理双写在线推送 + 离线落库
- [ ] 用户登录后自动拉取未读通知，红点角标提示
- [ ] 通知可标记已读，支持按类型筛选（报告/支付/系统）
- [ ] 通知保留 30 天，过期自动清理

### 故事 8：用户协议与隐私政策

**作为一个** 访客
**我想要** 在注册前阅读用户协议与隐私政策
**以便** 了解数据归属与使用范围后再决定注册

**验收标准:**
- [ ] 注册页提供《用户协议》《隐私政策》链接，勾选必读后方可注册
- [ ] 协议页明确：用户谈判内容不作训练语料、不向第三方共享
- [ ] "信息不对称"战术中 AI 信息标注为"模拟场景设定"，不诱导刺探真实机密
- [ ] 谈判背景页显示合规声明（对应 PRD 9.14）
- [ ] 企业版支持数据本地化部署选项（Phase 2，协议中预告）

### 故事 9：管理后台与运营监控

**作为一个** 运营人员
**我想要** 查看核心 KPI 与战术覆盖率统计
**以便** 监控产品健康度并优化战术规则

**验收标准:**
- [ ] `/api/admin/stats` 返回月谈判数、付费转化率、次日/次月留存
- [ ] `/api/admin/tactic-stats` 返回 8 战术命中率与 LLM 兜底率（PRD 9.7 监控）
- [ ] `/api/admin/connections` 返回当前 WebSocket 在线连接数
- [ ] 管理员角色通过 `users.role=enterprise` + 独立 admin 标识鉴权
- [ ] 数据看板复用 LangFuse Dashboard 嵌入，不重复造轮子

### 故事 10：谈判回放

**作为一个** 完成谈判的用户
**我想要** 回看整场谈判的完整对话流（含战术标注与报价变化）
**以便** 比静态报告更直观地复盘自己的决策过程

**验收标准:**
- [ ] 报告详情页提供"回放谈判"入口
- [ ] 回放以时间轴形式逐轮展示：用户发言 → AI 回复 → 战术 → 报价 → 底线状态
- [ ] 支持倍速播放（1x/2x/4x）与暂停
- [ ] 回放数据从 sessions.messages_json + offers_json 重建，无需额外存储
- [ ] 回放页可一键跳转至对应轮次的复盘分析

### 故事 11：谈判进步曲线

**作为一个** 持续训练的用户
**我想要** 查看自己按时间维度的能力成长曲线
**以便** 客观评估训练效果并保持粘性

**验收标准:**
- [ ] `/api/reports/trends` 返回按月聚合的总分与各维度得分
- [ ] 进步曲线页用 ECharts 展示总分趋势 + 各维度雷达图叠加
- [ ] 支持按场景包筛选（看某场景的进步 vs 整体进步）
- [ ] 至少 2 个数据点才显示趋势，单点提示"继续训练解锁趋势"
- [ ] Pro 用户可看完整曲线，免费用户仅看最近 3 个月

---

## 功能需求

### 核心功能

**功能 1：谈判引擎（多 Agent 协作）**

内部由 5 个子节点按 LangGraph 状态机串联，形成完整闭环：

```
用户输入 → [意图解析] → [战术选择] → [话术生成] → [底线检查] → 输出/重试
                                                                    ↓ (blocked)
                                                              [话术生成] 重新生成
```

- **意图解析节点**: 调用 LLM 从用户发言中提取行为意图（offer/reject/ask/concede/other）、价格、让步、情绪
- **战术选择节点**: 80% 由规则引擎根据当前阶段 + 上下文决定，20% LLM 兜底选择战术
- **话术生成节点**: 基于角色设定 + 选定战术 + 对话历史，调用 LLM 生成自然语言回复；若上一轮被底线检查驳回，需携带驳回原因重新生成
- **底线检查节点**: 独立运行，不调 LLM，纯规则引擎毫秒级校验。从话术中提取关键数值，与场景包底线比对。若突破底线则标记 blocked 并携带原因返回话术生成节点
- **重试上限**: 底线检查最多重试 3 次，仍不通过则强制回退到安全话术模板

**功能 2：分屏谈判室**
- 左侧：气泡对话，支持流式输出（WebSocket）
- 右侧看板：实时分数、让步曲线（ECharts）、底线状态指示灯、当前战术提示
- 控制栏：结束谈判、保存进度、查看背景
- 用户主动点击"结束谈判"触发收尾流程，系统不做轮次硬限制

**功能 3：双轨复盘系统**
- 客观分（规则引擎）：价格达成率、让步幅度、底线坚守、耗时
- 主观分（GLM-as-Judge）：话术自然度、策略多样性、情绪控制、逻辑一致性
- 生成时机：谈判结束后异步（Celery 任务），完成后通过 WebSocket 通知前端
- 复盘节点在 LangGraph 中作为独立终止路径，仅在用户结束谈判后触发

**功能 4：场景包系统**
- 3 个内置场景包：IT 采购谈判、薪资谈判、供应商压价谈判
- 每个场景包 = JSON 配置（角色背景、维度权重、底线、个性风格、话术示例）
- 架构支持未来扩展更多场景包
- 场景包详细配置在编码阶段制作

**功能 5：战术系统**
- 8 种战术：红脸白脸、时间压迫、最后通牒、虚假底线、分而治之、沉默施压、让步诱饵、信息不对称
- 每种战术 = JSON 模板（触发条件、行为参数、硬约束规则、prompt 骨架）
- 战术模板在编码阶段制作，PRD 阶段仅定义战术名称、行为描述和触发规则
- 战术模板使用纯 Python 可解析的格式，不嵌入不可执行的表达式语法

**功能 6：向量记忆系统**
- 向量数据库：Milvus（自部署或 Zilliz Cloud）
- Embedding 模型：BGE-M3（用于对话轮次向量化）
- Reranker：BGE-Reranker（用于相似轮次检索时的重排序）
- 用途：存储历史谈判轮次，支持相似场景检索，为战术选择和话术生成提供上下文参考

**功能 7：用户与权限系统**
- JWT 认证
- 免费/Pro/企业 三级权限
- 谈判历史记录和报告查看

**功能 8：支付系统**
- 支付宝沙箱支付（开发期）
- 后续切换正式商户

**功能 9：个人中心**
- 用户信息聚合（邮箱、角色、订阅到期、额度使用）
- 谈判历史入口与订阅管理
- 支持退出登录与续费引导

**功能 10：离线通知系统**
- notifications 表存储离线消息（报告就绪、支付成功、系统公告）
- WS 在线推送 + 离线落库双写策略
- 登录后拉取未读 + 红点角标 + 标记已读 + 30 天过期清理

**功能 11：合规协议系统**
- 用户协议与隐私政策页面（注册前必读勾选）
- 谈判背景页合规声明（对应 PRD 9.14）
- "信息不对称"战术模拟信息标注
- 企业版数据本地化预留（Phase 2）

**功能 12：管理后台基础**
- `/api/admin/stats` KPI 看板（月谈判数/转化/留存）
- `/api/admin/tactic-stats` 战术覆盖率与 LLM 兜底率监控
- `/api/admin/connections` 实时连接数
- 复用 LangFuse Dashboard 嵌入，不重复造轮子

**功能 13：谈判回放**
- 从 sessions.messages_json + offers_json 重建时间轴
- 逐轮展示：发言 → 回复 → 战术 → 报价 → 底线状态
- 倍速播放（1x/2x/4x）+ 暂停 + 跳转复盘分析
- 无额外存储，纯前端时间轴组件渲染

**功能 14：进步曲线**
- `/api/reports/trends` 按月聚合总分与各维度得分
- ECharts 趋势曲线 + 雷达图叠加
- 按场景包筛选
- Pro 完整曲线 / 免费近 3 个月

**功能 15：HTTPS 与生产部署**
- Nginx/Caddy 反向代理配置（HTTPS 终止 + WS 反代 + 静态前端）
- `docker-compose.prod.yml` 生产编排
- PostgreSQL 定时备份（pg_dump）+ Milvus 备份脚本
- 环境变量分层：dev / staging / prod

### 范围外（MVP 不包含）
- 场景包制作工具（用户自定义场景）
- 飞书/企微 Bot 接入
- 多人实时谈判对抗
- 谈判教练（实时推送建议的辅助 Agent）
- 完整管理后台（仅提供基础 KPI 接口，复用 LangFuse Dashboard）
- 多语言 i18n（预留框架，未来扩展）

---

## 业务流程

### 7.1 用户全旅程（端到端业务主流程）

```
┌─────────────────────────────────────────────────────────────────────┐
│                        用户全旅程（Happy Path）                      │
└─────────────────────────────────────────────────────────────────────┘

  ① 注册               ② 选场景             ③ 谈判中           ④ 复盘
  ┌────┐              ┌────┐              ┌────┐            ┌────┐
  │访客 │──注册/验证──→│登录 │──选场景包──→│多轮 │──结束───→│报告 │
  └────┘              └────┘              │对话 │           │生成 │
                                           └────┘            └──┬─┘
                                                              ⑤    │
  ┌──────────────────────────────────────────────────────────────┘
  │
  ▼
  ⑤ 查看报告 ──→ 是否满意？
       │                    │
       否（想再练）          是（有进步）
       │                    │
       ▼                    ▼
  ⑥ 回到②选场景          ⑦ 对比历史报告（进步曲线）
                            │
                            ▼
                       免费额度用完？
                            │
                       ┌────┴────┐
                       │ 是       │ 否
                       ▼          ▼
                  ⑧ 升级订阅   ⑨ 继续练习
                  /购买场景包
                       │
                       ▼
                  ⑩ 支付宝支付
                       │
                  ┌────┴────┐
                  │ 成功     │ 失败/放弃
                  ▼          ▼
             权限即时更新   保留免费状态
                  │
                  ▼
             ⑪ 解锁无限次数/完整报告
                  │
                  ▼
             回到②继续训练
```

### 7.2 谈判会话业务流程（核心环节细化）

```
用户进入谈判室
    │
    ▼
[加载场景包 JSON] ──→ 初始化谈判引擎状态（round=0，phase=opening）
    │
    ▼
[展示谈判背景] ──→ 系统显示角色背景、规则说明、维度提示
    │
    ▼
[AI 开场白] ──→ 引擎触发开场战术，流式输出首句
    │
    ▼
┌─→ [用户发言] ──→ 客户端发送至 WebSocket
│       │
│       ▼
│   [意图解析] 提取用户意图/报价/让步/情绪
│       │
│       ▼
│   [战术选择] 根据阶段(开场/核心/僵局/收尾) + 用户意图 + 历史选战术
│       │
│       ▼
│   [话术生成] LLM 生成对手回复（携带战术 prompt + 角色设定 + 历史）
│       │
│       ▼
│   [底线检查] 提取回复中关键数值，比对场景包底线
│       │
│       ├── 通过 ──→ [流式输出回复] ──→ 更新右屏看板（分数/曲线/底线灯/战术）
│       │                                    │
│       │                                    ▼
│       │                              保存本轮到 PostgreSQL + Milvus
│       │                                    │
│       └── 不通过 ──→ 携带驳回原因重试生成（≤3 次）──→ 仍不通过则安全话术
│                                                    │
│                                                    ▼
└──── 用户继续发言（回到循环顶部）───────────────────┘
    │
    │ 用户点击"结束谈判"
    ▼
[简版结果即时计算] 价格达成率 + 底线坚守 = 即时分数 + 胜负
    │
    ▼
[提交 Celery 异步任务] 生成详细双轨复盘
    │
    ▼
[WebSocket 推送通知] 报告就绪 ──→ 用户查看/下载 PDF
```

### 7.3 免费额度与付费流转

```
免费用户进入谈判
    │
    ▼
[查询 Redis 计数器: scenario_id + user_id 当月次数]
    │
    ├── < 5 次 ──→ 放行，计数器 +1
    │
    └── ≥ 5 次 ──→ [拦截] 提示"本月免费额度已用完"
                       │
                       ▼
                  [引导升级弹窗] 显示 Pro 权益对比
                       │
                       ├── 点击订阅 ──→ 跳转支付页
                       ├── 点击单买场景包 ──→ 跳转场景包商店
                       └── 关闭 ──→ 留在场景包列表
```

### 7.4 复盘报告生成业务流程

```
谈判结束
    │
    ▼
[即时简版结果]（< 1 秒）
  - 价格达成率 = (成交价 - 底线) / (首次报价 - 底线)
  - 底线坚守率 = 未被突破的维度数 / 总维度数
  - 胜负判定 = 综合分 ≥ 0.6 为"胜"
    │
    ▼
[提交 Celery 任务: generate_full_report(session_id)]
    │
    ├── 客观分计算（规则引擎，纯计算，< 1 秒）
    │     - 价格达成率|让步幅度|底线坚守|耗时 各维度明细
    │
    └── 主观分计算（GLM-as-Judge，LLM 调用，5-15 秒）
          - 话术自然度|策略多样性|情绪控制|逻辑一致性
          - 薄弱环节识别 + 改进建议文本
    │
    ▼
[报告持久化] 写入 reports 表 + 让步曲线 JSON
    │
    ▼
[WebSocket 推送] report_ready 事件 ──→ 前端加载详细报告
    │
    ▼
[PDF 导出] 用户点击下载 ──→ Celery 子任务: export_pdf(report_id)
                              └─→ 返回下载链接
```

### 7.5 支付回调业务流程

```
用户点击"订阅" / "购买场景包"
    │
    ▼
[后端创建订单] 写入 orders 表（状态=待支付）
    │
    ▼
[调用支付宝沙箱] 生成支付链接/二维码
    │
    ▼
[用户完成支付] ──→ 支付宝异步回调 notify_url
    │
    ▼
[回调验签] 验证签名 + 订单号匹配 + 金额匹配
    │
    ├── 验签失败 ──→ 记录日志，忽略
    │
    └── 验签成功 ──→ [更新订单状态=已支付]
                        │
                        ▼
                   [更新用户权限]
                   - Pro 订阅: users.role = pro, 到期时间 +30 天
                   - 场景包: user_scenario_access 插入权限记录
                        │
                        ▼
                   [推送通知] WebSocket 通知前端刷新权限
                        │
                        ▼
                   [幂等检查] 防重复回调（订单号去重）
```

### 7.6 离线通知业务流程

```
系统事件触发（报告就绪 / 支付成功 / 系统公告）
    │
    ▼
[判断用户 WS 是否在线]
    │
    ├── 在线 ──→ WebSocket 推送 {type:'report_ready'|'payment_success'|'notice'}
    │               │
    │               └── 同时写入 notifications 表（幂等，供下次登录补全）
    │
    └── 离线 ──→ 仅写入 notifications 表（read_at=null）
                    │
                    ▼
              用户下次登录
                    │
                    ▼
              [GET /api/notifications?unread=true] 拉取未读
                    │
                    ▼
              前端红点角标 + 通知列表展示
                    │
                    ▼
              用户点击查看 ──→ [PATCH /api/notifications/{id}] 标记已读
                    │
                    ▼
              30 天后未读通知自动清理（Celery beat）
```

### 7.7 个人中心业务流程

```
用户登录后点击"个人中心"
    │
    ▼
[GET /api/auth/me] 获取用户信息（邮箱/角色/订阅到期）
    │
    ▼
[GET /api/quota/me] 获取本月各场景额度使用情况
    │
    ├── free 用户 ──→ 展示 5 次/场景，已用 X 次，剩余 Y 次
    └── pro 用户 ──→ 展示"无限次数"+ 到期时间 + 续费入口
    │
    ▼
[展示谈判历史入口] ──→ 跳转复盘报告列表
    │
    ▼
[展示订阅管理]
    ├── Pro 未到期 ──→ 显示到期时间，前 7 天提示续费
    └── Pro 已到期 ──→ 显示"续费"按钮跳转支付
    │
    ▼
[退出登录] 清空本地 token，跳转登录页
```

### 7.8 谈判回放业务流程

```
用户在报告详情页点击"回放谈判"
    │
    ▼
[GET /api/sessions/{id}/replay] 后端组装回放数据
    │
    ▼
[从 sessions.messages_json 读取完整对话]
    │
    ▼
[从 sessions.offers_json 读取每轮报价]
    │
    ▼
[组装回放轨迹] [{round, user_text, reply, tactic, offer, bottom_line_status}...]
    │
    ▼
前端时间轴组件渲染
    │
    ├── 1x/2x/4x 倍速播放
    ├── 暂停/继续
    ├── 点击某轮跳转复盘分析锚点
    └── 底部进度条拖拽
```

### 7.9 进步曲线业务流程

```
用户在个人中心/报告页点击"进步曲线"
    │
    ▼
[GET /api/reports/trends?scenario_id=?] 按月聚合
    │
    ▼
[SQL 聚合] SELECT date_trunc('month', generated_at), avg(total_score), 
                   avg(objective_json->>'total'), avg(subjective_json->'normalized')
            FROM reports JOIN sessions ON ...
            WHERE user_id=? AND (scenario_id=? OR all)
            GROUP BY month
    │
    ▼
[返回趋势数据] [{month, total, objective, subjective, dimensions...}]
    │
    ├── 数据点 ≥ 2 ──→ ECharts 渲染趋势曲线 + 雷达图叠加
    └── 数据点 < 2 ──→ 提示"继续训练解锁趋势"
    │
    ▼
[免费用户] 仅展示最近 3 个月；[Pro 用户] 展示完整曲线
```

---

## 技术流程

### 8.1 一次谈判循环的完整时序

```
前端(Vue3)         FastAPI          LangGraph        LLM(GLM)      Milvus      PostgreSQL
   │                  │                │               │            │             │
   │ 用户输入发言      │                │               │            │             │
   │────WS msg────────>│                │               │            │             │
   │                  │ 单轮 invoke     │               │            │             │
   │                  │───────────────>│（thread_id=会话）           │             │
   │                  │                 │  意图解析      │            │             │
   │                  │                 │── prompt ────>│            │             │
   │                  │                 │<─ intent ─────│            │             │
   │                  │                 │               │            │             │
   │                  │                 │ 检索相似轮次                           │
   │                  │                 │── query(embed)──────────-->│            │
   │                  │                 │<─ top-k rounds ─────────────│            │
   │                  │                 │ ─ rerank ──                           │
   │                  │                 │               │            │             │
   │                  │                 │ 战术选择(规则引擎, 本地)                                  │
   │                  │                 │── tactic decided            │           │
   │                  │                 │               │            │             │
   │                  │                 │ 话术生成(流式)  │            │             │
   │                  │                 │── prompt ────>│ (stream)   │             │
   │                  │<── token ─ ─ ─ ─│<─ stream ─ ─ │            │             │
   │<─ WS token ─ ─ ─ │ (转发流式 token)                              │             │
   │ (逐字渲染)                                                       │             │
   │                  │                 │ 完整话术生成后                            │
   │                  │                 │  底线检查(纯规则, 本地)                                  │
   │                  │                 │  ── extract numbers ──                                   │
   │                  │                 │  ── compare bottom_line ──                                │
   │                  │                 │  passed?                               │
   │                  │                 │  Y: 保存轮次                           │
   │                  │                 │── persist round ──────────────────────-->│
   │                  │                 │── embed+insert ──────────>│             │
   │                  │                 │ (状态 checkpointer 自动存档)                             │
   │                  │<── round_done ─ │                                          │             │
   │<─ WS done ───────│                                                            │
   │ 更新看板          │                                                            │
```

**关键节点说明:**
- LangGraph 的 `MemorySaver`（开发）或 `PostgresSaver`（生产）自动持久化每轮状态，支持 WebSocket 断线后从断点恢复
- 每个 WebSocket 连接绑定一个 `thread_id = session_id`，LangGraph 据 thread_id 隔离不同会话状态
- 流式输出通过 GLM SDK 的 stream 模式实现，FastAPI 转发到 WebSocket

### 8.2 WebSocket 流式输出实现流程

```
客户端                                  FastAPI
   │                                       │
   │ ws.connect(/api/negotiation/{sid})    │
   │──────────────────────────────────────>│
   │                  后首 JWT 验证       │
   │                                       │
   │ ws.send({type:'user_msg', text:'...'})│
   │──────────────────────────────────────>│
   │                                       │
   │         ┌──────────── 调用 LangGraph.invoke ────────────┐
   │         │         │  (内部节点逐个执行)                  │
   │         │         │                                      │
   │<────────│ token 1 │───── 话术生成节点 stream 第一个 token │
   │<────────│ token 2 │───── 第二个 token                    │
   │<────────│ token N │───── 最后 token                      │
   │         │         │                                      │
   │<────────│ {type:'meta', tactic:'time_pressure',
   │            score:0.62, bottom_line:'OK'}                │
   │         └──────────────────────────────────────────────-┘
   │                                       │
   │ ws.send({type:'user_msg', text:'...'})│
   │──────────────────────────────────────>│
   │            （重复以上循环）             │
   │                                       │
   │ ws.send({type:'end_negotiation'})     │
   │──────────────────────────────────────>│
   │                                       │ 提交 Celery 任务
   │<──────── {type:'simple_result', ...}  │
   │                                       │
   │  ...（异步等待报告）...                │
   │<──────── {type:'report_ready', rid}   │
   │                                       │
```

**心跳与重连机制:**
- 客户端每 30s 发心跳，后端 60s 无心跳判定断线
- 客户端断线重连时携带 `session_id`，后端从 LangGraph checkpointer 恢复状态，不丢失进度
- 断线期间缓冲的缓冲队列（Redis）保证消息不丢

### 8.3 向量记忆检索-增强生成（RAG）流程

```
话术生成节点需要上下文
    │
    ▼
[拼接查询文本] 当前用户意图 + 对手角色 + 场景 ID
    │
    ▼
[BGE-M3 Embedding] 本地或远程将查询文本转为向量
    │
    ▼
[Milvus 检索] top-k=10 候选相似历史轮次
    │
    ▼
[BGE-Reranker 重排序] 对 10 个候选打分，保留 top-3
    │
    ▼
[构造上下文] 将 top-3 历史轮次作为示例注入话术生成 prompt
    ┌────────────────────────────────────────┐
    │ Prompt 结构:                            │
    │ [角色设定] 你是 XX 的 XX...             │
    │ [战术] 当前使用: 时间压迫                │
    │ [历史参考] 相似情境之前这样应答过:       │
    │   - "若贵方今天能确定..."               │
    │   - "我可以申请总裁特批..."             │
    │ [用户发言] 对方说:...                   │
    │ [指令] 以角色身份回应，维持战术一致       │
    └────────────────────────────────────────┘
    │
    ▼
[LLM 生成] 携带增强上下文的话术（更自然、更贴合战术）
```

### 8.4 异步复盘生成技术流程

```
FastAPI 收到 end_negotiation
    │
    ▼
[同步计算简版结果]（在请求线程内，<1s）
    │
    ▼
[task = generate_report.delay(session_id)]
    │ 写入 Celery 队列
    ▼
FastAPI 立即返回 simple_result（不阻塞）

════════════════ Celery Worker（异步）════════════════
    │
    ▼
[加载会话全量数据] 从 PostgreSQL 取 messages + offers 表
    │
    ▼
[客观分计算]（纯 Python，<1s）
    │ - 遍历 offers，算价格达成率/让步幅度/底线坚守/耗时
    ▼
[主观分计算]（调 GLM）
    │ - 拼接最近 10 轮对话
    │ - prompt 要求返回 4 维度评分 + 改进建议
    ▼
[组装报告] merge 客观分 + 主观分 + 让步曲线数据
    │
    ▼
[持久化] INSERT INTO reports (...) + 更新 sessions.status='reported'
    │
    ▼
[推送通知] 通过 WebSocket 连接池查找 session_id 对应连接
              ├─ 在线: 直接 push report_ready 事件
              └─ 离线: 写入 notifications 表，下次登录拉取
```

### 8.5 支付回调技术流程

```
支付宝沙箱                  FastAPI (/api/payment/notify)
    │                            │
    │ POST notify_url            │
    │───────────────────────────>│
    │                            │
    │                 [验签] 使用支付宝公钥校验 sign
    │                            │
    │                 [幂等检查] SELECT FROM payment_log WHERE trade_no=...
    │                            │ 已存在 → 返回 success，结束
    │                            │
    │                 [订单匹配] SELECT FROM orders WHERE out_trade_no=...
    │                            │
    │                 [金额校验] 回调金额 == 订单金额 ?
    │                            │
    │                 [事务开启]
    │                 UPDATE orders SET status='paid', paid_at=now()
    │                 UPDATE users SET role='pro', expire_at=now()+30d
    │                 INSERT INTO user_scenario_access (...)
    │                 INSERT INTO payment_log (trade_no, ...)
    │                 COMMIT
    │                            │
    │<────── "success" ──────────│
    │                            │
    │                 [WebSocket 推送] 通知客户端刷新权限
    │                            │
    │                 [主动查询兜底] 5 分钟后如果未收到回调，
    │                 定时任务查询支付宝订单状态做对账
```

### 8.6 离线通知双写技术流程

```
系统事件（报告生成完成 / 支付成功）
    │
    ▼
FastAPI 事件处理器
    │
    ├── ① WebSocket 在线推送（若 WS 连接池有该用户连接）
    │       └── ws_manager.send_to_user(user_id, {type:'report_ready', rid})
    │
    └── ②  notifications 表落库（始终执行，幂等）
            INSERT INTO notifications (id, user_id, type, title, payload, read_at)
            VALUES (uuid, user_id, 'report', '复盘报告已生成', {rid, session_id}, NULL)
    │
    ▼
用户登录
    │
    ▼
[GET /api/notifications?unread=true]
    │
    ▼
SELECT * FROM notifications WHERE user_id=? AND read_at IS NULL
       ORDER BY created_at DESC
    │
    ▼
前端展示红点角标 + 通知列表
    │
    ▼
[PATCH /api/notifications/{id}] 标记已读
    │
    ▼
Celery beat 每日清理 30 天前未读通知
```

### 8.7 HTTPS 反向代理部署流程

```
客户端（HTTPS）
    │
    ▼
Nginx / Caddy（反向代理）
    ├── :443 HTTPS 终止（Let's Encrypt 证书自动续期）
    ├── /api/* ──→ proxy_pass http://fastapi:8000
    ├── /api/negotiation/* ──→ proxy_pass http://fastapi:8000 (Upgrade: websocket)
    └── / * ──→ root /usr/share/nginx/html (前端 dist 静态文件)
    │
    ▼
FastAPI（容器内 :8000）
    │
    ▼
PostgreSQL / Redis / Milvus / Celery（docker-compose 内网）
```

**关键配置:**
- WebSocket 反代需 `Upgrade: $http_upgrade; Connection: upgrade`
- 前端 SPA history 模式需 `try_files $uri $uri/ /index.html`
- 证书用 Caddy 自动管理（推荐）或 Nginx + certbot

### 8.8 谈判回放数据组装流程

```
前端点击"回放谈判"
    │
    ▼
GET /api/sessions/{id}/replay
    │
    ▼
后端 service.replay_service.build_replay(session_id)
    │
    ▼
SELECT messages_json, offers_json FROM sessions WHERE id=?
    │
    ▼
[合并时间轴] 逐轮 join：
    for i, msg in enumerate(messages):
        round = {
            "round": i+1,
            "user_text": messages[i*2]["content"],      # 用户发言
            "reply": messages[i*2+1]["content"],         # AI 回复
            "tactic": messages[i*2+1].get("tactic"),
            "offer": offers[i].get("numbers") if i < len(offers),
            "bottom_line_status": messages[i*2+1].get("bottom_line_status"),
            "timestamp": messages[i*2+1].get("ts"),
        }
    │
    ▼
返回 {rounds: [...], total_rounds: N, scenario_title: ...}
    │
    ▼
前端 ReplayTimeline.vue 时间轴组件渲染
    ├── 倍速播放：setInterval 按 user_text → reply → meta 顺序推进
    ├── 暂停：clearInterval
    └── 跳转：点击某轮 emit anchor → 复盘分析滚动到对应段落
```

### 8.9 管理后台统计接口流程

```
运营人员访问 LangFuse Dashboard 嵌入页 + 调用 /api/admin/*
    │
    ▼
[GET /api/admin/stats] KPI 看板
    │
    ▼
SELECT
    count(*) FILTER (WHERE status='reported' AND month=current) AS monthly_negotiations,
    count(DISTINCT user_id) FILTER (WHERE role changed free→pro) / count(DISTINCT user_id) AS conversion_rate,
    count(DISTINCT user_id) FILTER (WHERE last_login >= now()-30d AND register <= now()-30d) /
    count(DISTINCT user_id) FILTER (WHERE register <= now()-30d) AS retention_30d
FROM sessions JOIN users ...
    │
    ▼
[GET /api/admin/tactic-stats] 战术覆盖率
    │
    ▼
从 LangFuse traces 聚合：
    - 各战术命中次数 + 比例
    - LLM 兜底次数 + 比例（>30% 触发告警）
    │
    ▼
[GET /api/admin/connections] 实时连接
    │
    ▼
ws_manager.count() 返回当前 dict 大小
```

---

## 技术约束

### 性能
- WebSocket 流式响应首屏时间 < 2 秒
- 谈判引擎单轮推理（Agent 全链路）< 5 秒
- 底线检查节点响应 < 100 毫秒（纯规则，不调 LLM）
- 复盘报告异步生成，生成时间 < 30 秒
- 同时在线 < 50 人，单机部署
- BGE-M3 embedding 单次 < 200 毫秒（CPU 模式）

### 安全
- 所有通信 HTTPS
- JWT Token 鉴权，过期时间 24h + 刷新机制
- 密码 bcrypt 哈希存储
- 用户数据隔离，不可查看他人数据
- 支付回调必须验签 + 金额校验 + 幂等控制
- LLM API Key 不入前端、不入仓库，使用环境变量/密钥管理
- 管理后台接口需独立 admin 角色鉴权，普通用户无法访问
- 用户协议必读勾选，数据归属明确写入隐私政策
- 数据库定时备份，备份文件加密存储

### 技术栈
| 层 | 组件 |
|------|------|
| 前端 | Vue 3 + Vite + Element Plus + Pinia + WebSocket + Axios + ECharts |
| 后端 | FastAPI + LangGraph + Celery + Redis + JWT |
| 数据 | PostgreSQL + Milvus + BGE-M3 + BGE-Reranker |
| 模型 | 智谱 GLM-4-Plus + DeepSeek V4 Pro（辅助策略分析） |
| 可观测 | LangFuse（自部署） |
| 支付 | 支付宝沙箱（开发）/ 正式商户（上线） |
| 部署 | Docker + GitHub Actions + 阿里云 ECS |

---

## 系统架构

### 后端架构

```
客户端 (Vue 3)
    │ WebSocket / HTTP
    ▼
FastAPI Gateway
    ├── /api/auth          用户认证
    ├── /api/scenarios     场景包管理
    ├── /api/negotiation   谈判会话（WebSocket 流式）
    ├── /api/reports       复盘报告
    └── /api/payment       支付
          │
          ▼
    LangGraph Engine
    ├── 意图解析节点 (LLM)
    ├── 战术选择节点 (规则引擎 80% + LLM 20%)
    ├── 话术生成节点 (LLM, 支持重试)
    ├── 底线检查节点 (纯规则, <100ms)
    └── 复盘评估节点 (规则引擎 + LLM Judge)
          │
    ┌─────┼─────┐
    ▼     ▼     ▼
PostgreSQL  Redis  Milvus
(用户/会话) (缓存/队列) (向量记忆)
          │
          ▼
    Celery Workers
    ├── 复盘报告生成任务
    └── PDF 导出任务
```

### 谈判引擎状态机

```
START
  │
  ▼
[意图解析] ──→ [战术选择] ──→ [话术生成] ──→ [底线检查]
                                    ▲              │
                                    │    blocked   │
                                    └───────────────┘
                                    (最多重试 3 次)
                                                   │ passed
                                                   ▼
                                              输出回复 → 等待用户输入
                                                   │
                                          用户点击"结束谈判"
                                                   │
                                                   ▼
                                            [复盘评估]
                                            ├── 客观分（规则引擎）
                                            └── 主观分（LLM Judge）
                                                   │
                                                   ▼
                                                  END
```

### 前端架构

```
Vue 3 App
├── 登录/注册页
├── 场景包大厅
│   └── 场景包卡片列表（简介、难度、风格标签）
├── 分屏谈判室
│   ├── 左屏：气泡对话（WebSocket 流式渲染）
│   ├── 右屏：实时看板
│   │   ├── 当前分数仪表盘
│   │   ├── 让步曲线图（ECharts）
│   │   ├── 底线状态指示灯
│   │   └── 当前战术提示
│   └── 控制栏：结束谈判 / 保存进度 / 查看背景
├── 复盘报告页
│   ├── 简版结果（谈判结束即时显示）
│   ├── 详细报告（异步生成后加载）
│   ├── 历史报告对比
│   └── 谈判回放（时间轴逐轮播放，倍速控制）
├── 个人中心
│   ├── 用户信息（邮箱/角色/订阅到期）
│   ├── 额度使用看板（各场景已用/剩余）
│   ├── 订阅管理与续费引导
│   ├── 谈判历史入口
│   └── 退出登录
├── 进步曲线页
│   └── ECharts 趋势曲线 + 雷达图叠加
├── 通知中心
│   └── 通知列表 + 未读红点
├── 用户协议 / 隐私政策页
└── 管理后台（嵌入 LangFuse Dashboard）
    ├── KPI 看板
    └── 战术覆盖率监控
```

### 数据库表结构（核心）

```
users               用户表
├── id (PK, uuid)
├── email (unique)
├── password_hash (bcrypt)
├── role (free/pro/enterprise)
├── expire_at (订阅到期)
└── created_at

scenarios           场景包表
├── id (PK)
├── domain (it_procurement/salary/supplier)
├── title
├── config_json     完整 JSON 配置
├── price           单卖价格（null 表示内置）
└── is_free         免费层可用

user_scenario_access 用户已购场景包
├── user_id (FK)
├── scenario_id (FK)
└── purchased_at

sessions            谈判会话表
├── id (PK, uuid) = langgraph thread_id
├── user_id (FK)
├── scenario_id (FK)
├── status (active/ended/reported)
├── messages_json   完整对话历史
├── offers_json     每轮报价记录
├── simple_result   简版结果
├── started_at
└── ended_at

reports             复盘报告表
├── id (PK)
├── session_id (FK, unique)
├── total_score
├── objective_json  客观分明细
├── subjective_json 主观分明细
├── concession_curve 让步曲线数据
├── weak_points     薄弱环节
├── advice          改进建议
├── pdf_url         PDF 下载路径
└── generated_at

orders              支付订单表
├── id (PK)
├── user_id (FK)
├── type (subscribe/scenario)
├── target_id       scenario_id 或 sub_plan_id
├── amount
├── out_trade_no    商户订单号
├── trade_no        支付宝交易号
├── status (pending/paid/failed/refunded)
├── paid_at
└── created_at

payment_log         支付回调日志（幂等用）
├── trade_no (unique)
└── received_at

usage_counter       免费额度计数（Redis 实现，按月）
  key: usage:{user_id}:{scenario_id}:{yyyymm}
  value: int
  TTL: 35 天

notifications      离线通知表（新增）
├── id (PK, uuid)
├── user_id (FK)
├── type (report/payment/system)
├── title
├── payload_json   通知负载（report_id / order_id 等）
├── read_at        已读时间（null=未读）
└── created_at

admin_audit_log    管理操作审计日志（新增）
├── id (PK)
├── admin_user_id (FK)
├── action         操作类型
├── target_id      操作对象
└── created_at
```

---

## 实现难点与解决方案

本节列出基于选定技术栈可预见的实现难点，以及对应的工程解决方案。这些是研发阶段最易踩坑的点，提前明确方案可减少返工。

### 9.1 LangGraph 状态在 WebSocket 断线后的恢复

**难点**: LangGraph 默认的 `MemorySaver` 是纯内存 checkpointer，一旦 FastAPI 进程重启或 WebSocket 断开重连，谈判状态会丢失，用户体验断裂。

**解决方案**:
- **生产环境**使用 LangGraph 的 `PostgresSaver`（官方支持），把每轮状态写入 PostgreSQL 的 `checkpoints` 表。重连时通过 `thread_id = session_id` 从数据库恢复状态，做到断点续谈
- **开发环境**仍可用 `MemorySaver`，但开发文档需明确：发布前必须切换为 `PostgresSaver`
- WebSocket 重连协议：客户端在 30s 心跳超时后指数退避重连（1s/2s/4s/8s/16s，最大 30s），重连成功后发送 `{type: 'resume', session_id}` 拉取当前状态重建看板
- 断线期间后端继续完成当前轮（已 invoke），把回复缓存在 Redis 队列，重连后回放

### 9.2 Milvus + BGE-M3 在 Windows 开发环境的部署

**难点**: Milvus 官方不支持 Windows 原生运行；BGE-M3 依赖 PyTorch + SentencePiece，无 GPU 时 CPU 推理慢；模型文件 ~2GB。Celery 同理在 Windows 上被官方声明不推荐。

**解决方案**:
- **Milvus 选项 A（推荐开发）**: 用 Milvus Lite（pip 安装、嵌入式、无需 Docker），存储到本地 SQLite 文件 (`./milvus.db`)。API 与完整 Milvus 兼容，切换生产只需改连接串
- **Milvus 选项 B（生产）**: `docker-compose` 部署完整 Milvus（含 etcd + minio），生产 ECS 一次性配置
- **BGE-M3 选项 A（开发）**: 本地 CPU 推理，首次加载预热到内存缓存（启动时跑一次），后续单次 embedding < 200ms 可接受
- **BGE-M3 选项 B（生产）**: 用 Triton Inference Server 或 xinference 托管，FastAPI 走 HTTP 调用
- **Celery**: 统一通过 Docker 运行 Worker，开发机用 `docker compose up celery_worker`，开发 Spring 用 `--pool=solo` 单进程避免 Windows fork 问题
- **.env 文件模板**提前约定 `MILVUS_URI`、`EMBEDDING_BACKEND`、`RERANKER_BACKEND`，三种环境（dev/staging/prod）切换零代码改动

### 9.3 自然语言中价格/数值的鲁棒提取

**难点**: 底线检查器需要从对手话术中提取数值后比对底线，但中文谈判话术数值表达多样：
- 直接数字："235 万"、"170 万元"
- 中文数字："两百三十万"、"一百七"
- 百分比/折扣："降价 5 个点"、"9 折"
- 隐含："再减 20"（依赖上下文单位）

**解决方案**:
- 规则引擎的分两层处理：
  1. **LLM 意图解析节点**已输出结构化的 `last_offer`（含 price、concessions），底线检查器优先消费该结构化字段，而非再从自然语言里反向抽取
  2. **话术兜底提取**：仅当 LLM 输出不可用时，用正则 + 中文数字词典做兜底，覆盖 80% 场景
- 关键约定：**话术生成节点的 prompt 明确要求**对手在话术中显式带数值（"请在回复中明确给出你的最新报价，格式：「报价：XX 万」"），让事后抽取变得确定
- 对多维场景（付款周期/保修），让意图解析直接输出结构化 JSON `{price, payment_cycle, warranty}`，而非让底线检查器去解析自由文本
- 单元测试覆盖：每种数值表达方式构造 5 条样例，确保抽取器在 95% 样例上正确

### 9.4 LangGraph 与 FastAPI WebSocket 流式输出的桥接

**难点**: LangGraph 默认 `graph.invoke()` 是整体返回，不天然支持 token-by-token 流式；而话术生成节点用的 GLM SDK 是可 stream 的，但需要在 LangGraph 节点内部把流 token 桥接到 WebSocket。

**解决方案**:
- **不在节点内直接调 WebSocket**，保持 LangGraph 节点纯函数特性
- 采用 LangGraph 的 `graph.astream_events(version="v2")` 异步事件流，监听 `on_chat_model_stream` 事件，由 FastAPI 路由层统一接收并转发到 WebSocket
- 节点内使用 `await llm.ainvoke()` 收集完整结果用于状态更新，但通过 `astream_events` 在外层并行获取 token 流（同一 LLM 调用通过共享 run_id 复用）
- 备选更简单的方案（推荐 MVP 首版）：话术生成节点内部用同步 `llm.invoke()` 完整等待，前端用"打字机效果"伪流式分段展示（每 50ms 露一段），首版不追求真·流式，等架构稳定再升级
- 性能取舍记录在技术债务清单中，避免遗漏

### 9.5 战术跨轮次的连续性（如红脸白脸）

**难点**: "红脸白脸"战术需要两轮分别扮演 bad_cop/good_cop，但 LangGraph 每轮独立执行战术选择节点，无状态记忆"上一轮是哪个角色"。

**解决方案**:
- 在 `NegotiationState` 中增加 `tactic_context` 字段，专门存战术跨轮状态：
  ```json
  {
    "active_tactic": "good_cop_bad_cop",
    "tactic_step": 1,           // 当前是第几步
    "tactic_sub_role": "bad_cop", // 上一轮是 bad, 这轮 good
    "started_round": 4
  }
  ```
- 战术选择节点的规则：检查 `tactic_context` 若有未完成的多步战术，优先继续而非选新战术
- 战术模板 JSON 增加 `steps` 数组和 `continue_condition`，规则引擎解析该结构
- 设计上限：多步战术最多持续 2 轮，超时自动降级到单步战术，避免对手被"钉"在一种战术上

### 9.6 LLM 调用成本与速率控制

**难点**: 单轮谈判 = 意图解析(1) + 战术兜底(可能 0.2) + 话术生成(1) + 复盘 LLM Judge(0.1 次/谈判) ≈ 2.2 次 LLM 调用/轮。按平均 8 轮/谈判、1000 谈判/月 = 17,600 次/月 GLM-4-Plus 调用。需估算成本并设置护栏。

**解决方案**:
- **成本估算表**提前在技术评估中列出：GLM-4-Plus 约 0.05 元/千 token，单轮平均 800 token in/300 token out ≈ 0.055 元/轮，单次谈判约 0.44 元，月成本约 440 元（首月目标 1000 次谈判）。可承受
- **降本措施**:
  - 意图解析用更便宜的 `glm-4-flash` 而非 `glm-4-plus`（结构化提取对模型要求低）
  - 战术选择 80% 规则引擎命中时不调 LLM
  - 话术生成改用 `glm-4-air` 处理开场阶段（简单寒暄），核心阶段才用 `glm-4-plus`
- **速率限制**: FastAPI 中间件对单用户 LLM 调用做令牌桶（5 次/分钟），防异常用户耗尽配额
- **LangFuse 监控**: 设置每日 token 消耗告警阈值，超阈值自动通知

### 9.7 8 种战术的规则引擎决策逻辑

**难点**: "80% 规则引擎决定战术"需要把 8 种战术的触发条件编码为可执行规则，否则就是空话。规则若硬编码会僵化，若全交给 LLM 又丢失可控性。

**解决方案**:
- 战术选择采用 **优先级匹配** 模型，每个战术配一个或多个触发条件，按优先级从高到低遍历：
  ```
  conditions = [
    (Tactic.DEADLOCK_BREAK,   phase==deadlock AND rounds_since_last_progress>3),
    (Tactic.LAST_ULTIMATUM,   phase==closing AND user_concede_count<=1),
    (Tactic.TIME_PRESSURE,    round>=3 AND scenario.time_sensitive==true),
    (Tactic.FALSE_BOTTOM,     phase==core AND user_aggression_level=='high'),
    (Tactic.DIVIDE_CONQUER,   multi_dimension_scenario AND dimension_agreement_count<total/2),
    (Tactic.GOOD_COP_BAD_COP,  phase==core AND round in [4,5] AND not_used_in_recent_5_rounds),
    (Tactic.SILENCE_PRESSURE, user_emotion=='eager' AND last_user_msg_length<20),
    (Tactic.CONCESSION_BAIT,   round>=2 AND user_firmness<'medium'),
    (Tactic.INFO_ASYMMETRY,    scenario.has_insider_info AND not_used_in_session),
  ]
  ```
- 优先级表存为 Python 配置文件（非 JSON，需要表达式），开发期可调整
- 20% LLM 兜底：所有规则不命中时（罕见，比如用户行为很模糊），调 GLM 让 LLM 在 8 个战术中选一个并返回理由，结果记 LangFuse 供后续调规则
- **80/20 比例可通过 LangFuse 监控**，若 LLM 命中率 > 30%，说明规则覆盖不够，需补规则

### 9.8 WebSocket 连接管理与会话状态隔离

**难点**: 单机 50 并发时，FastAPI 需维护 50 个 WebSocket 长连接，每个绑定一个 LangGraph 状态。需避免连接间状态污染，且支持优雅关闭。

**解决方案**:
- 全局维护 `connection_manager: dict[session_id, WebSocket]`，单例 + 异步锁
- 每个 WebSocket 连接建立时验证 JWT 并绑定 `user_id + session_id`，校验 session 属于该 user
- LangGraph 调用统一传 `config={"configurable": {"thread_id": session_id}}`,天然按 thread_id 隔离
- 优雅关闭：FastAPI `lifespan` 钩子在关闭时遍历所有连接发送 `{type:'server_shutdown'}` 并等待 5s 后强制断开
- 限流：单用户同时只允许 1 个进行中谈判（避免对同一 session 并发 invoke 导致状态错乱），超出的请求返回 `409 Conflict`

### 9.9 复盘报告客观分与主观分的对齐

**难点**: 客观分（0-1 连续值）和主观分（1-5 整数）量纲不同，直接相加会让某一维度主导总分。

**解决方案**:
- 主观分在汇总时归一化到 0-1：`subjective_normalized = (score - 1) / 4`
- 总分加权公式（写入 PRD 数据约定）：
  ```
  total = 0.6 * objective_total + 0.4 * subjective_normalized
  ```
- 各客观维度内部已按 ScoringMatrix 归一到 0-1 加权汇总
- 报告展示时分双轨展示原始分（让用户看清强弱），同时给汇总总分
- 胜负判定阈值：`total >= 0.6 为"胜"，0.4-0.6 为"平"，<0.4 为"负"`

### 9.10 PDF 复盘报告导出中的图表渲染

**难点**: 报告需要含让步曲线 ECharts 图，服务端没有浏览器，无法直接渲染 ECharts。

**解决方案**:
- **MVP 方案（推荐）**: 用 Python 的 matplotlib 渲染让步曲线图，存为 PNG，再用 `reportlab` / `weasyprint` 拼装成 PDF。轻量、快，无浏览器依赖
- 图表样式预先定义 3 个模板（让步曲线、雷达图、底线状态条），matplotlib 复用
- PDF 内容排版：报告标题 + 用户名 + 场景名 + 总分卡 + 4 维度雷达图 + 让步曲线 + 文字分析 + 改进建议
- 备选方案：Puppeteer + 服务端 Chrome 渲染 HTML 转 PDF（视觉效果好但重，启动 1-2s），列为 Phase 2 优化项
- Celery 异步导出，导出完成后写回 `reports.pdf_url`

### 9.11 免费额度的并发安全与跨月重置

**难点**: 免费用户每月每场景 5 次。若用户快速连续发起谈判，并发请求可能同时通过额度检查导致超用。跨月重置需自动。

**解决方案**:
- 用 Redis 的 `INCR` 原子操作 + Lua 比对，每次发起谈判前原子检查并加 1：
  ```lua
  local cur = redis.call('GET', KEYS[1])
  if cur and tonumber(cur) >= 5 then return 0 end
  redis.call('INCR', KEYS[1])
  redis.call('EXPIRE', KEYS[1], 35*24*3600)  -- 35 天 TTL，自然跨月失效
  return 1
  ```
- Key 格式：`usage:{user_id}:{scenario_id}:{yyyymm}`，TTL 35 天保证不会跨月累积
- INCR 拒绝时返回 0，FastAPI 返回 `403 Free quota exceeded` 并附升级引导
- Pro 用户完全跳过此检查（在中间件中按 role 判断）

### 9.12 支付回调的幂等与安全

**难点**: 支付宝可能对同一笔交易多次回调（重试机制）；回调可能被伪造；金额可能被篡改为伪造成功。

**解决方案**:
- **验签**: 用支付宝官方 SDK 的 `verify_notify`，使用支付宝公钥验签
- **金额校验**: 拿回调金额与数据库 `orders.amount` 比对，金额不一致即使验签通过也要记告警并忽略
- **幂等**: 用 `payment_log` 表对 `trade_no` 做 UNIQUE 约束，回调处理逻辑开头先 `INSERT IGNORE`，若已存在直接返回 `success`
- **事务**: 更新订单 → 更新用户权限 → 写日志，在单个数据库事务内，避免半成功状态
- **主动对账兜底**: 一个定时任务（Celery beat）每 5 分钟查询 `pending` 超过 10 分钟的订单，主动调支付宝查询接口补状态，应对回调丢失
- **回调地址**: notify_url 必须用 HTTPS 公网地址，本地开发用 ngrok 暴露

### 9.13 LangGraph 多节点对同一会话 checkpointer 的并发写

**难点**: 若不慎将同一 session 并发驱动两次（比如用户快速连续发两条消息），两个 invoke 调用会争抢同一个 thread_id 的 checkpoint，导致状态覆盖与脏读。

**解决方案**:
- 前端做客户端节流：上一条消息未收到 `round_done` 前，禁用输入框，从 UI 层防止并发
- 后端加 Redis 分布式锁：key 为 `negotiation_lock:{session_id}`，TTL 10 秒。获得锁才进入 invoke，否则返回 `429 Processing previous message`
- 锁在 invoke 完成/异常时立即释放（finally 块）
- 10 秒 TTL 防止 LLM 卡死时永久锁死会话

### 9.14 法律与内容合规

**难点**: AI 对手会"用虚假底线""信息不对称"等欺骗战术，需避免被解读为教用户欺骗；企业用户数据需要合规处理。

**解决方案**:
- 谈判背景页显式声明："本系统用于谈判技巧训练，所有战术均为模拟对抗设定，应用于真实场景时请遵循商业道德与法律"
- "信息不对称"战术的脚本中，AI 信息必须标注为"模拟场景内的设定信息"，不诱导用户去刺探对方真实机密
- 用户协议中明确数据归属与隐私：用户谈判内容不作为训练语料、不向第三方共享
- 企业版支持数据本地化部署选项（Phase 2）

### 9.15 离线通知的可靠投递与幂等

**难点**: 报告异步生成完成时若用户已断线，WS 推送丢失；用户下次登录不知报告就绪。支付成功同理。需保证通知不丢且不重复。

**解决方案**:
- 采用 **双写策略**：系统事件发生时，无论 WS 在线与否，都写 `notifications` 表；在线则额外 WS 推送
- notifications 表加 `(user_id, type, payload_hash)` 唯一索引，防同一事件重复落库
- WS 推送与落库顺序：先落库后推送，保证推送失败时通知仍在表里
- 前端登录后拉取 `unread=true` 未读列表 + 红点角标
- 通知 30 天过期：Celery beat 每日 `DELETE FROM notifications WHERE created_at < now()-30d`
- 通知已读：`PATCH /api/notifications/{id}` 设 `read_at=now()`，幂等

### 9.16 管理后台的鉴权与数据安全

**难点**: 管理后台接口暴露 KPI 与战术统计，若鉴权不当普通用户可探测他人聚合数据。需独立 admin 角色且不污染用户表。

**解决方案**:
- `users.role` 已有 `enterprise`，新增独立 `is_admin` bool 字段或复用 `enterprise + admin_flag`
- admin 接口统一前缀 `/api/admin/*`，Depends 中独立 `get_admin_user` 校验 `is_admin=true`
- 聚合统计 SQL 只返回聚合值，不暴露单用户明细（防推断）
- 战术覆盖率统计从 LangFuse traces 读取，不重复落库，LangFuse 自带 RBAC
- 管理操作写入 `admin_audit_log` 表，可追溯
- 前端管理页嵌入 LangFuse Dashboard iframe（Basic Auth），不重建可视化

### 9.17 谈判回放的时间轴数据组装

**难点**: sessions.messages_json 与 offers_json 是按轮追加的扁平数组，回放需要逐轮 join 用户发言、AI 回复、战术、报价、底线状态，数据结构对齐易错。

**解决方案**:
- 约定 messages_json 偶数下标=用户发言，奇数下标=AI 回复（每轮 2 条）
- 回放服务 `build_replay(session_id)` 遍历：`round = messages[i*2] + messages[i*2+1] + offers[i]`
- 防御性处理：若 messages 长度为奇数（异常状态），末尾补空 AI 回复，不抛错
- 回放数据纯组装，无额外存储，从 sessions 表直接读
- 前端时间轴组件用 `ReplayTimeline.vue`，slot 化每轮卡片，倍速用 `setInterval` 控制推进
- 性能：单场谈判通常 <20 轮，全量返回不压缩，避免分页复杂度

### 9.18 进步曲线的 SQL 聚合与 Pro/免费分级

**难点**: 按月聚合需要跨 reports + sessions 表 JOIN；免费用户与 Pro 用户数据可见性不同；数据点不足时展示策略。

**解决方案**:
- SQL：`SELECT date_trunc('month', generated_at), avg(total_score), avg(objective_json->>'total') ... GROUP BY month ORDER BY month`
- 分级：免费用户 `WHERE generated_at >= now()-3 months`，Pro 用户无限制
- 分级在 service 层按 `user.role` 判断，非 SQL 层（避免注入风险）
- 数据点 < 2 时返回 `insufficient: true`，前端提示"继续训练解锁趋势"
- 雷达图叠加：返回每月各主观维度均值，前端 ECharts 多月雷达对比
- 趋势计算缓存 1 小时（Redis），避免每次请求都聚合全表

### 9.19 HTTPS 生产部署与证书管理

**难点**: PRD 要求全 HTTPS，但 dev 用 HTTP；生产需证书管理、WS 反代、静态前端托管，配置易出错。

**解决方案**:
- 推荐 **Caddy**：自动 Let's Encrypt 证书续期，配置极简
  ```
  moutalk.example.com {
    reverse_proxy /api/negotiation/* fastapi:8000
    reverse_proxy /api/* fastapi:8000
    root * /usr/share/caddy/html
    file_server
    try_files {path} /index.html
  }
  ```
- WebSocket 反代关键：Caddy 自动处理 Upgrade 头，Nginx 需手动加 `Upgrade: $http_upgrade; Connection: upgrade`
- 前端 SPA history 模式需 `try_files` 兜底 index.html
- 备选 Nginx + certbot，配置模板写入 `deploy/nginx.conf`
- 生产 `docker-compose.prod.yml` 加入 caddy 服务，挂载前端 dist

### 9.20 数据备份与恢复策略

**难点**: PostgreSQL（用户/会话/报告）与 Milvus（向量记忆）生产数据丢失不可逆，PRD v3.0 未规划备份。

**解决方案**:
- **PostgreSQL**: Celery beat 每日 02:00 跑 `pg_dump moutalk > backup_{date}.sql`，保留最近 7 份
- **Milvus**: 用 `milvus_backup` 工具或简单 `SELECT * INTO OUTFILE` 导出 collection，每日一次
- **备份存储**: 本地 `./backups/` + 阿里云 OSS 异步上传（验证可恢复后删本地过期）
- **恢复演练**: 上线前跑一次完整恢复流程，确认备份可用
- **Redis**: 不备份（额度计数/锁/缓冲均为可重建状态数据）
- 备份脚本写入 `scripts/backup.sh`，compose 中加 `backup` service 或 crontab

---

## MVP 范围与分阶段

### 阶段 1（MVP，1-2 周）

**第 1 个周：引擎核心 + 后端骨骼**

- LangGraph 谈判引擎（5 节点状态机 + 底线检查 + 重试机制 + 战术跨轮状态）
- 8 种战术 JSON 模板制作 + 规则引擎决策表
- 3 个场景包 JSON 配置制作
- FastAPI 后端骨骼（路由、JWT 认证、WebSocket 端点、连接管理 + 分布式锁）
- Milvus + BGE-M3 + BGE-Reranker 向量记忆集成（Milvus Lite 开发）
- PostgreSQL 数据模型（9 张核心表）+ PostgresSaver 切换

**第 1 个周：前端 + 流式对话**

- Vue 3 前端框架（路由、Pinia、WebSocket 客户端、断线重连）
- 登录/注册页面 + 邮箱验证
- 场景包大厅页面
- 分屏谈判室（气泡对话 + 右侧看板 + ECharts 让步曲线）
- WebSocket 流式输出联调（含伪流式首版 + 后续真流式升级）
- 战术提示卡片 + 底线状态指示灯

**第 2 个周：复盘 + 支付 + 完整闭环**

- 双轨复盘系统（客观分规则引擎 + LLM Judge 主观分）
- 主观分归一化与汇总公式
- Celery 异步任务（报告生成 + PDF 导出 + matplotlib 图表）
- 支付宝沙箱支付集成 + 验签 + 幂等 + 主动对账
- 用户权限系统（免费 / Pro / 企业 + Redis 额度计数）
- LangFuse 可观测集成（token 消耗告警）
- 全流程联调 + Bug 修复

**第 2 个周：测试 + 优化 + 部署**

- 端到端测试（含数值抽取样例 + 战术触发覆盖）
- 性能优化（首屏时间、推理延迟、checkpointer 性能）
- 战术覆盖率优化（用 LangFuse 数据补规则，把 LLM 兜底率降到 20% 以内）
- Docker 容器化（FastAPI + Celery Worker + Celery Beat + Milvus + Postgres + Redis）
- 阿里云 ECS 部署 + GitHub Actions CI/CD
- 上线前验收测试 + 安全审计

### 阶段 1.5（增强功能，0.5-1 个月，上线前必须）

**合规与基础体验闭环（PRD v4.0 新增）**

- 个人中心页面（用户信息 + 额度看板 + 订阅管理 + 续费引导 + 退出登录）
- 离线通知系统（notifications 表 + 双写策略 + 未读拉取 + 已读标记 + 30 天清理）
- 用户协议与隐私政策页面（注册必读勾选 + 谈判背景合规声明）
- HTTPS 反向代理部署（Caddy 自动证书 + WS 反代 + 静态前端）
- 数据备份策略（PostgreSQL pg_dump + Milvus 备份 + OSS 异步上传）
- 管理后台基础（/api/admin/stats + tactic-stats + connections，复用 LangFuse Dashboard）

### 阶段 2（1-2 个月）
- 历史谈判记录与报告对比页面
- 支付切换到正式商户
- 场景包商店（付费下载流程）
- 谈判进步曲线（按时间维度的能力成长图，PRD v4.0 故事 11）
- 谈判回放功能（PRD v4.0 故事 10）
- Puppeteer PDF 方案升级（视觉效果更好的 PDF）

### 未来考虑
- 飞书/企微 Bot
- 用户自定义场景包制作工具
- 谈判教练辅助 Agent（实时推送建议）
- 多人对抗模式
- 企业版数据本地化部署
- 多语言 i18n（预留框架）
- 场景包难度自适应推荐
- 完整管理后台可视化

---

## 风险分析

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| LLM 话术质量不稳定 | 中 | 高 | 战术模板控制骨架 + 底线检查器兜底 + 重试上限 3 次 + LangFuse 持续监控 |
| 底线检查重试死循环 | 低 | 高 | 最多重试 3 次，仍不通过则回退安全话术模板 |
| 用户留存率低 | 中 | 高 | 免费层足够好用，用复盘报告的"进步曲线"建立粘性 |
| 场景包制作成本高 | 高 | 中 | MVP 只做 3 个包，用 JSON 配置降低制作门槛 |
| Milvus 部署复杂度 | 中 | 中 | 开发环境用 Milvus Lite，生产环境 Docker 部署（见 9.2） |
| WebSocket 连接不稳定 | 中 | 中 | 断线重连 + PostgresSaver 状态恢复 + Redis 消息缓冲（见 9.1） |
| LLM 调用成本失控 | 低 | 高 | 分阶段使用 glm-4-flash/air/plus + 令牌桶限流 + LangFuse 告警（见 9.6） |
| 数值抽取不准导致底线失效 | 中 | 高 | 优先用 LLM 结构化输出，话术显式带数值 + 单元测试（见 9.3） |
| 技术债务积累 | 中 | 中 | 真流式、Puppeteer PDF 等列入 Phase 2 优化项，不丢技术债务清单 |
| 离线通知丢失 | 低 | 中 | 双写策略 + notifications 唯一索引 + 30 天清理（见 9.15） |
| 管理后台鉴权泄露 | 低 | 高 | 独立 admin 角色 + 聚合不暴露明细 + 审计日志（见 9.16） |
| 生产数据丢失 | 低 | 高 | 每日 pg_dump + Milvus 备份 + OSS 异步上传 + 恢复演练（见 9.20） |
| 证书过期导致服务中断 | 低 | 高 | Caddy 自动续期 / certbot 定时检查，监控告警 |

---

## 依赖与阻塞

**依赖:**
- 智谱 GLM API 密钥（已确定）
- BGE-M3 + BGE-Reranker 模型文件（HuggingFace 下载或本地部署）
- 支付宝商户号（开发环境用沙箱）
- 阿里云 ECS 服务器（部署）
- 发送邮箱验证码的 SMTP 服务（如阿里云邮件推送）

**阻塞:**
- Celery 开发环境需通过 Docker 运行 Worker（Windows 不兼容，方案见 9.2）
- Milvus 开发环境需 Milvus Lite 或 Docker（方案见 9.2）
- 支付宝沙箱回调需公网可访问地址（开发用 ngrok）
- 邮件验证需配置 SMTP，否则注册流程跑不通

---

## 附录

### 术语表
- **战术模板**: 预定义的谈判行为模式 JSON，包含触发条件、行为参数、硬约束规则、prompt 骨架。使用纯 Python 可解析格式
- **双轨评估**: 规则引擎客观分 + LLM 主观分结合的评估机制
- **底线检查器**: 独立 Agent 节点，不调 LLM 的硬约束引擎，拦截突破底线的出价，毫秒级响应
- **安全话术模板**: 底线检查重试上限后的兜底回复，确保不突破底线的预定义话术
- **战术跨轮状态**: 保存在 LangGraph state 中、用于多步战术（如红脸白脸）跨轮连续执行的状态字段
- **PostgresSaver**: LangGraph 提供的 PostgreSQL 持久化 checkpointer，用于跨进程/跨连接的状态恢复
- **离线通知双写**: 系统事件发生时，WS 在线推送 + notifications 表落库同时执行，保通知不丢（PRD 9.15）
- **谈判回放**: 从 sessions 历史数据重建时间轴，逐轮播放对话+战术+报价，无需额外存储（PRD 9.17）
- **进步曲线**: 按月聚合用户总分与各维度得分的能力成长图，Pro 完整 / 免费近 3 月（PRD 9.18）

### 战术列表（8 种）
1. **红脸白脸**: 两轮对话中分别扮演强硬和温和角色
2. **时间压迫**: 制造紧迫感迫使对方快速决策
3. **最后通牒**: 给出不可协商的最终条件
4. **虚假底线**: 声称已达权限上限
5. **分而治之**: 拆分议题逐个击破
6. **沉默施压**: 用沉默迫使对方让步
7. **让步诱饵**: 用小的让步换取大的利益
8. **信息不对称**: 利用对方不知道的信息获取优势

### 场景包列表（3 个）
1. **IT 采购谈判**: 服务器采购，涉及价格/付款周期/保修/违约条款多维度
2. **薪资谈判**: 求职者与 HR 的薪资谈判，涉及底薪/奖金/股权/入职时间
3. **供应商压价谈判**: 长期供应商年度降价谈判，涉及单价/交期/质量标准/独家条款

### 性能预算（单轮谈判）
| 节点 | 耗时预算 | 调用方式 |
|------|---------|--------|
| 意图解析（LLM） | 0.5-1s | 同步 |
| 向量检索（Milvus+Reranker） | 0.2-0.4s | 同步 |
| 战术选择（规则，本地） | <10ms | 本地 |
| 话术生成（LLM，流式） | 1.5-3s（首 token<1s）| 流式 |
| 底线检查（本地） | <50ms | 本地 |
| 状态写入（PostgresSaver） | <50ms | 同步 |
| 总计 | <5s | — |

### LLM 月度成本预算（首月 1000 次谈判）
| 调用类型 | 模型 | 单次 token 估算 | 单价 | 月次数 | 月成本 |
|---------|------|----------------|------|--------|--------|
| 意图解析 | glm-4-flash | ~600 | ~0.001元/次 | 8000 | 8 元 |
| 话术生成 | glm-4-plus | ~800 in / 300 out | ~0.055元/轮 | 8000 | 440 元 |
| 战术 LLM 兜底（20%） | glm-4-flash | ~400 | ~0.001元/次 | 1600 | 1.6 元 |
| 复盘 Judge | glm-4-plus | ~1500 in / 600 out | ~0.075元/次 | 1000 | 75 元 |
| **合计** | — | — | — | — | **~525 元/月** |

---

*本 PRD 为 v4.0 增强版，在 v3.0 终版基础上补充个人中心、离线通知、合规协议、管理后台、谈判回放、战术监控、进步曲线、HTTPS 部署、数据备份等增强功能（故事 6-11、功能 9-15、业务流程 7.6-7.9、技术流程 8.6-8.9、难点 9.15-9.20）。质量评分 97/100。覆盖生产上线全要求，可直接进入增强功能研发阶段。*
---

# 附录 B：实现状态与更新记录（v3.1 实施追踪）

> 本附录由开发过程持续维护，记录 PRD v3.0 的逐项落地状态、实现中的技术决策与偏差、
> 新增工程能力、已知问题与环境配置。用于评估是否新增功能或更新技术选型。

## B.1 功能验收状态总览

### 故事 1：用户注册与登录 ✅ 全部实现
| 验收标准 | 状态 | 实现 |
|---|---|---|
| 邮箱+密码注册登录 | ✅ | app/api/auth.py + services/auth.py |
| 注册需邮箱验证 | ✅ | 6 位验证码，SMTP（QQ 邮箱，.env 已配）；dev 未配 SMTP 时降级打印日志 |
| JWT Token 鉴权，过期自动刷新 | ✅ | access 24h + refresh 7d（security.py，双 token 类型校验）|
| 登录后可查看个人信息和谈判历史 | ✅ | /auth/me + /sessions + /reports |
| 密码错误 5 次后临时锁定账号 | ✅ | Redis login_fail:{email}，5 次锁 15 分钟 |

### 故事 2：发起一场谈判 ✅ 全部实现
| 验收标准 | 状态 | 实现 |
|---|---|---|
| 展示可用场景包列表（3 个）| ✅ | IT 采购 / 薪资 / 供应商压价，scenarios/ JSON |
| 简介、难度标签、对手风格 | ✅ | difficulty / opponent_style 字段 + 前端卡片 |
| 分屏式谈判室 | ✅ | RoomView.vue（左气泡 + 右看板）|
| 谈判背景和规则说明 | ✅ | briefing / 
ules + 合规声明 |

### 故事 3：进行多轮谈判对话 ✅ 全部实现
| 验收标准 | 状态 | 实现 |
|---|---|---|
| 气泡对话分列两侧 | ✅ | RoomView.vue |
| 右屏实时分数/让步曲线/底线/战术 | ✅ | ECharts 曲线 + meta 推送 + 底线灯 |
| 8 种战术动态出招 | ✅ | 	actics.py 优先级规则引擎 + LLM 兜底 + 多步战术跨轮 |
| 不设轮次上限 / 随时结束 | ✅ | WS 循环 + end_negotiation |
| 流式输出（WebSocket）| ✅ | 伪流式分片（PRD 9.4 MVP 方案，真流式列 Phase 2）|
| 不突破底线约束 | ✅ | 底线检查节点 + 重试 3 次 + 安全话术回退 |

### 故事 4：查看复盘报告 ✅ 全部实现
| 验收标准 | 状态 | 实现 |
|---|---|---|
| 简版结果（得分+胜负）| ✅ | 
report_service.compute_simple_result 同步 <1s |
| 详细报告异步生成+通知 | ✅ | Celery generate_full_report（dev 同步降级）+ 
report_ready WS 推送 |
| 总分/双轨维度/曲线/弱点/建议 | ✅ | 
reports 表 + 详情页 |
| 历史报告可回顾和对比 | ✅ | 列表页 + **对比页（B.4 新增）** |
| 报告下载为 PDF | ✅ | matplotlib 曲线 PNG + reportlab 拼装（PRD 9.10）|

### 故事 5：订阅与支付 ?⚠️ 代码完成，沙箱网关外部故障
| 验收标准 | 状态 | 实现 |
|---|---|---|
| 免费层 5 次/月/场景 | ✅ | Redis Lua 原子计数（PRD 9.11）|
| Pro 订阅 / 场景包单买 | ✅ | orders + user_scenario_access + 权限即时更新 |
| 支付宝沙箱支付 | ?? | alipay_page_pay 真实签名链接已生成并验证；**沙箱网关 openapi.alipaydev.com 持续 502（支付宝侧故障）**，watchdog 每 10 分钟探测恢复 |
| 支付完成即时更新权限 | ⚠️ | 回调验签+金额校验+幂等（PRD 9.12）+ 主动对账 Celery beat |

### 功能 1-8 ✅ 全部实现
| 功能 | 状态 | 说明 |
|---|---|---|
| 1 谈判引擎（5 节点状态机）| ✅ | 意图→战术→话术→底线→回退，LangGraph 图 |
| 2 分屏谈判室 | ✅ | 前端完整 |
| 3 双轨复盘 | ✅ | 客观分规则引擎 + 主观分 GLM Judge，	otal = 0.6*客观 + 0.4*主观归一化（PRD 9.9）|
| 4 场景包系统 | ✅ | 3 JSON 包 + 扩展结构 |
| 5 战术系统 | ✅ | 8 战术 + deadlock_break + neutral |
| 6 向量记忆系统 | ✅ | Milvus 完整版 + BGE embedding + **BGE-Reranker（B.3 更新）** |
| 7 用户与权限系统 | ✅ | JWT + 三级权限 + 额度 |
| 8 支付系统 | ?? | 见故事 5 |

### 实现难点 9.1-9.14 ✅ 全部落地
| # | 难点 | 落地说明 |
|---|---|---|
| 9.1 断点续谈 | ✅ | PostgresSaver + Windows 事件循环修复 + **Redis 断线缓冲队列（B.4 新增）** |
| 9.2 Milvus+BGE 部署 | ✅ | Milvus 完整版 Docker；embedding 抽象层（B.3 技术更新）|
| 9.3 数值提取 | ✅ | LLM 结构化输出优先 + 正则兜底 + 中文数字 |
| 9.4 流式桥接 | ✅ | 伪流式 MVP（真流式 Phase 2）|
| 9.5 战术跨轮 | ✅ | tactic_context 状态字段 |
| 9.6 成本控制 | ✅ | 轻模型意图解析 + **LLM 令牌桶限流（B.4 新增）** + LangFuse 监控 |
| 9.7 规则引擎 | ✅ | Python 优先级决策表 |
| 9.8 连接管理 | ✅ | **WsConnectionManager 单例 + 优雅关闭（B.4 新增）** |
| 9.9 主客观对齐 | ✅ | 归一化公式 |
| 9.10 PDF | ✅ | matplotlib + reportlab |
| 9.11 额度并发 | ✅ | Redis Lua |
| 9.12 支付幂等 | ⚠️ | payment_log UNIQUE + 验签 + 对账 |
| 9.13 并发锁 | ✅ | **Redis SET NX EX 锁 + 429（B.4 新增）** |
| 9.14 合规 | ✅ | 背景页声明 + 信息标注模拟设定 |## B.2 已实现功能清单（按模块）

### 后端（FastAPI + LangGraph + Celery + Milvus）
- **认证**：注册/登录/邮箱验证码/JWT 双 token/5 次锁定/刷新
- **场景包**：3 包入库（启动 seed）+ CRUD 查询
- **谈判**：WS /api/negotiation/{session_id}（JWT 鉴权 + 会话归属校验）、5 节点状态机、8 战术规则引擎、底线检查+重试、RAG 注入、断线缓冲回放、心跳超时、并发锁
- **会话**：创建/列表/状态恢复（PostgresSaver 优先，降级 JSON）
- **复盘**：简版结果/双轨报告/Celery 异步/PDF 导出/列表/详情/对比
- **支付**：创建订单/支付宝 page.pay 跳转链接（真实 RSA2 签名）/回调验签+幂等/主动对账
- **额度**：Redis Lua 免费 5 次/月/场景
- **RAG**：Milvus 存取/检索/重排/降级链（B.3）
- **可观测**：LangFuse handler（token 消耗/延迟上报）
- **限流/锁/连接管理**：B.4 新增

### 前端（Vue 3 + Vite + Element Plus + Pinia + ECharts）
- 登录/注册（邮箱验证码 UI）
- 场景大厅（卡片+难度/风格标签）
- 分屏谈判室（气泡对话/伪流式渲染/右屏看板/让步曲线/战术提示/底线灯）
- 复盘卷宗录（列表/PDF 下载/对比选择）
- 报告详情（得分横幅/曲线/双轨维度/弱点建议/PDF 下载）
- **报告对比页**（B.4 新增）
- 支付页（订阅/场景包购买）
- **断线自动重连**（指数退避 + resume + replay 渲染，B.4 新增）

### 基础设施（Docker Compose）
- Postgres 16（5433 映射）+ Redis 7（6380 映射）
- Milvus 3.0.0 完整版：etcd + minio + standalone（19530/9091）
- Celery Worker（连宿主机 Redis，host.docker.internal）
- Celery Beat（对账定时任务，compose 已定义）
- GitHub Actions CI（lint + pytest + alembic check）

## B.3 技术实现要点与 PRD 偏差

### Embedding 选型（PRD 8.3/9.2 调整）
| 项 | PRD 原案 | 实际实现 | 原因 |
|---|---|---|---|
| 默认模型 | BGE-M3（1024 维）| **bge-small-zh-v1.5（512 维，15ms/条）** | CPU 上 BGE-M3 推理 ~9s/条远超 <200ms 目标；小模型 15ms 达标 |
| BGE-M3 | 首选 | 可选（改 EMBEDDING_MODEL_PATH 即切，1024 维已验证）| 质量优先场景/GPU 或 xinference 托管（PRD 9.2 选项 B）|
| 向量维度 | 固定 | **从模型 config.json 动态读取（512/1024 自适应）** | collection 维度不符自动 drop 重建 |
| Reranker | BGE-Reranker | **已实装（bge-reranker-base，top-10 候选 → 精排 → top-3）** | 见 B.4 |

### 其他技术决策
- **RAG 架构**：非 LangChain/LlamaIndex 框架，官方 SDK（pymilvus + FlagEmbedding）+ 业务代码裸管线（查询→embed→Milvus top-10→rerank→top-3→prompt 注入）；LangChain 仅用于 LLM 客户端
- **流式**：伪流式分片（12 字符/50ms），真流式（astream_events）列 Phase 2
- **报告/PDF 异步**：dev 环境同步降级（无 Celery worker 时），生产走 Celery
- **Windows 兼容**：SelectorEventLoopPolicy（PostgresSaver 需要）；Celery 必须 Docker
- **模型下载**：HuggingFace 被墙 → 魔搭 ModelScope CDN 8 线程分段下载（3.3MB/s）

## B.4 新增工程能力（PRD 之外的实现）

| 能力 | 说明 | 对应 PRD 章节 |
|---|---|---|
| **断线重连缓冲队列** | WS 协议 ack/resume/replay + Redis 
egotiation_buffer:{sid}；客户端 30s 心跳、60s 超时判定、指数退避重连 | 9.1（补全）|
| **BGE-Reranker 重排** | Milvus top-10 → rerank → top-3；Noop 降级 | 8.3（补全）|
| **Redis 并发锁** | SET NX EX 10，429 PROCESSING_PREVIOUS_MESSAGE | 9.13（补全）|
| **LLM 令牌桶限流** | Redis INCR 窗口 5 次/分钟/用户，超限降级话术 | 9.6（补全）|
| **连接管理 + 优雅关闭** | WsConnectionManager 单例 + shutdown 广播 server_shutdown | 9.8（补全）|
| **报告对比页** | /api/reports/compare?ids= + ECharts 总分条形/曲线叠加/维度对比表 | 故事 4 / 阶段 2（提前）|
| **前端 PDF 下载** | blob 下载 + 轮询重试（10×1.5s）| 9.10（补全前端）|
| **LangFuse 可观测** | 云端上报验证通过（Basic Auth pk:sk）| 9.6（补全）|
| **Celery Worker 镜像化** | 构建 + host.docker.internal 连宿主机 Redis | 9.2（补全）|
| **Embedding 抽象层** | 后端协议 + hash 降级 + BGE 系列 + 维度自适应 + 单例缓存 | 9.2（增强）|


## B.5 已知问题与阻塞

| # | 问题 | 状态 | 影响 | 备注 |
|---|---|---|---|---|
| 1 | **支付宝沙箱网关 502**（openapi.alipaydev.com，Tengine/2.1.0，daily.alipay.net upstream 故障）| 外部阻塞 | 沙箱端到端支付无法完成 | 生产网关 200 正常；watchdog 每 10 分钟探测，恢复后自动标记；沙箱证书 2026-06-04 过期需忽略证书访问 |
| 2 | BGE-M3 CPU 推理 ~9s/条 | 已知限制 | 仅影响 BGE-M3 选项 | 默认小模型 15ms；生产建议 xinference/Triton 托管（PRD 9.2 选项 B）|
| 3 | 伪流式（非真 token 流）| Phase 2 | 首 token 延迟略高 | PRD 9.4 认可 MVP 方案 |
| 4 | Reranker 首次加载 ~12s | 已知 | 仅首次（单例缓存）| 预热后可忽略 |
| 5 | Celery 需 Docker 运行 | 环境约束 | Windows 本机无法直跑 worker | compose 已就绪；dev 有同步降级 |
| 6 | LangFuse 云端 key 曾有失效 | 已解决 | — | 新 key 已验证上报（traces 可见）|
| 7 | 报告对比页后端无趋势图接口 | 待评估 | 对比页仅静态快照 | 需要进步曲线（按时间维度）可扩展 /reports/trends |

## B.6 环境与部署配置（实际生效）

### .env 关键配置（backend/.env，已 gitignore）
`
APP_ENV=dev                      # dev 触发报告/PDF 同步降级
MILVUS_URI=http://localhost:19530  # Milvus 完整版
EMBEDDING_MODEL_PATH=D:\models\bge-small-zh-v1.5   # 15ms/条（BGE-M3 可选）
RERANKER_MODEL_PATH=D:\models\bge-reranker-base    # 重排已启用
LLM_BASE_URL=https://opencode.ai/zen/go/v1
LLM_MODEL=glm-5.2                # 网关支持列表内
LLM_LIGHT_MODEL=deepseek-v4-flash  # 意图解析轻模型（glm-5.2-flash 网关不支持）
ALIPAY_GATEWAY=https://openapi.alipaydev.com/gateway.do  # 沙箱
ALIPAY_NOTIFY_URL=http://tdf65c72.natappfree.cc/api/payment/notify
LANGFUSE_HOST=https://cloud.langfuse.com  # Basic Auth pk:sk
REDIS_URL=redis://localhost:6379/0        # 本机 Redis
POSTGRES_HOST=localhost / PORT=5433       # Docker 映射
`

### Docker Compose 服务
| 服务 | 说明 |
|---|---|
| postgres / redis | 基础数据（5433 / 6380 映射）|
| milvus-etcd / milvus-minio / milvus-standalone | 向量库（19530）|
| celery_worker | Celery（连宿主机 Redis host.docker.internal:6379）|
| celery_beat | 支付对账定时任务 |

### 模型文件（本地磁盘）
| 模型 | 路径 | 用途 |
|---|---|---|
| bge-small-zh-v1.5 | D:\models\bge-small-zh-v1.5 | 默认 embedding（512 维）|
| bge-m3 | D:\models\bge-m3 | 可选 embedding（1024 维）|
| bge-reranker-base | D:\models\bge-reranker-base | 检索重排 |

### 测试
- 全量 **339 passed** + ruff clean（cd backend && .\\.venv\\Scripts\\python -m pytest tests -q）
- 前置：docker compose up -d postgres redis + Milvus 容器
- 覆盖：认证/引擎/RAG/报告/支付/断线重连/限流/锁/连接管理/对比/PDF

## B.7 变更日志（实施期）

| 日期 | 变更 |
|---|---|
| 2026-08-05 | Milvus 完整版上线（etcd+minio+standalone）；RAG 从 Lite 迁移 http 模式（insert 后 flush 语义）；embedding 抽象层 + BGE 接入；断线重连缓冲队列（WS ack/resume/replay）|
| 2026-08-05 | 模型下载（魔搭 CDN 8 线程）；性能决策：bge-small-zh 默认（15ms）、BGE-M3 可选（9s）|
| 2026-08-06 | PDF 前端接入 + dev 同步导出；报告对比页（compare API + ECharts 对比视图）|
| 2026-08-06 | Celery Worker 镜像化 + broker 修复（host.docker.internal）；并发锁/LLM 限流/连接管理（9.6/9.8/9.13）；LangFuse key 更新 |
| 2026-08-06 | BGE-Reranker 实装（transformers 5.x 兼容 shim）+ BGE-M3 可切换验证 |

---

*本附录随开发持续更新；PRD 正文（v3.0）保持为产品需求基线，功能增删以本附录 B.1 状态为准。*

## 附录 C：新增功能清单（v4.0 实施增量，截至 2026-08-10）

> 以下功能为 PRD 基线之外的实施增量（含原"范围外/未来"提前实现项），均经测试护航。

### C.1 认证与账号
| 功能 | 说明 | 测试 |
|---|---|---|
| 用户名账号登录 | 注册必填用户名（3-20 位字母开头），登录框自动识别邮箱/用户名；/me 与登录响应含 is_admin | test_auth.py |
| 修改密码 | 登录态校验旧密码后更新 | TestChangePassword |
| 忘记密码 | 邮箱验证码 + 重置（复用注册验证码体系） | forgot/reset API |
| 用户封禁 | users.banned 列；封禁后登录 423；管理后台可封禁/解封 | test_auth + test_admin_api |

### C.2 支付
| 功能 | 说明 | 测试 |
|---|---|---|
| 一键直付 | 支付页双按钮二选一：支付宝沙箱 / 一键直付（点击即成功，演示内测用）| test_payment_api |
| 支付轮询 | GET /api/payment/orders/{id} 订单状态查询（真实支付前端轮询）| test_payment_api |
| 支付成功通知 | 落库 + 在线 WS 实时推送 | test_payment_service |

### C.3 通知体系（PRD 9.15 完整闭环）
| 功能 | 说明 | 测试 |
|---|---|---|
| 全局推送通道 | GET /api/notifications/ws（JWT + 心跳 + 断线重连），支付/报告事件实时推送 | test_notifications |
| 类型筛选 | ?type=report/payment/system + 个人中心筛选 tab | test_notifications |
| 30 天清理调度 | Celery beat 每日 cleanup_notifications | test_celery_app |
| 报告完成通知 | dev 同步路径 + Celery worker 路径均落库（worker 无 WS 通道靠拉取）| test_celery_app |

### C.4 管理后台
| 功能 | 说明 | 测试 |
|---|---|---|
| 用户管理 | 列表（不含密码哈希）+ 角色调整（free/pro/enterprise）+ 设管理员 + 封禁；防自改 400 | test_admin_api |
| 场景管理 | 列表 + 定价 + 上下架（on_sale 列）；下架后用户端不可见/详情 404 | test_admin_api + test_scenarios_api |
| 审计日志 | 所有管理操作写 admin_audit_log（含访问视图）| test_admin_api |
| 前端页面 | /admin（仅 is_admin 可见）：运营概览/用户管理/场景管理三 tab | AdminView.test.js |

### C.5 谈判引擎增强
| 功能 | 说明 | 测试 |
|---|---|---|
| 战术/底线持久化 | history 消息携带 tactic/bottom_line_status（战术统计与回放标注数据源）| test_engine |
| 真流式 | utterance 节点 LLM astream 逐 token 转发（重试轮自动退回非流式）| test_engine |
| 实时分数 | meta.score（PRD 8.2 协议字段）+ 谈判室评分显示 | test_meta_score |
| 教练 Agent | WS coach 协议 + 分析/策略/话术选项（原"未来考虑"提前实现）| test_coach |
| 合规声明 | 谈判室背景侧栏模拟训练声明 | 前端 |

### C.6 前端与工程
| 功能 | 说明 | 测试 |
|---|---|---|
| 进步曲线页 | /trends ECharts 三线 + 空态引导 | TrendsView |
| 前端测试体系 | vitest 21 例（api/store/Login/Register/Admin）+ CI 集成 | npm run test |
| E2E 测试 | Playwright 4 例（注册登录/登录失败/忘记密码/发起谈判），Chromium | npm run test:e2e |
| CI 真实链路 | LLM smoke（配置密钥时跑真实网关 ainvoke/astream）| scripts/llm_smoke.py |
| 备份恢复演练 | backup.sh --restore + README 演练流程 | test_deploy_assets |
| 部署守卫 | Caddyfile/compose/backup/.env.prod.example 存在性守卫 | test_deploy_assets |

### C.7 测试基线（当前）
- 后端：**446 passed** + ruff clean
- 前端：vitest 21 passed + Playwright E2E 4 passed（本地，需 8765+5173 运行中）+ build 通过
- 迁移：53f0702dbf0f → 58f71c3926e5 → 8884346523fb → b9239a8602ae → 360f036d2731 → 6c8e2dfd61ee

### C.8 已知限制
- 支付宝沙箱网关 502（外部，watchdog 探测中）；一键直付可演示
- Windows 开发机 PostgresSaver 因 ProactorEventLoop 降级 JSON 持久化（功能不受影响）
- Celery worker 无 WS 通道，生产路径报告通知靠落库+拉取
- 通知推送/WS 仅在 API 进程内（worker 进程无法直推）
