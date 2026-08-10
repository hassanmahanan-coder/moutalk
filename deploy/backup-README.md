# 数据备份策略（PRD 9.20）

## PostgreSQL（用户/会话/报告——核心数据）
- 脚本：`scripts/backup.sh`（pg_dump）
- 调度：Celery beat 每日 02:00 或 crontab
- 保留：最近 7 份，自动清理
- 备份存储：本地 `./backups/` + 可选阿里云 OSS 异步上传

## Milvus（向量记忆——可重建数据）
- 原始轮次完整存于 Postgres `sessions.messages_json`，向量 collection 可随时从历史重建
- 完整备份：官方 milvus-backup 工具（https://github.com/zilliztech/milvus-backup）
- 恢复演练：上线前跑一次完整恢复流程

## Redis（额度/锁/缓冲——可重建状态数据）
- 不备份（额度跨月自然失效；锁/缓冲为瞬时数据）

## 备份
```bash
./scripts/backup.sh                 # 备份（默认保留 7 份）
./scripts/backup.sh --retain 14     # 自定义保留份数
```

## 恢复演练（PRD 9.20 流程项，建议每月一次）
```bash
# 1) 先备份当前数据（恢复前快照）
./scripts/backup.sh

# 2) 恢复到 Postgres 容器（--restore 模式）
./scripts/backup.sh --restore backups/moutalk_pg_YYYYMMDD_HHMMSS.sql

# 3) 验证
#    - 后端健康检查：curl http://localhost:8765/health
#    - 抽样检查：登录一个老账号，确认报告/会话/额度仍可访问
#    - 开一局新谈判确认写入正常（恢复后写链路未损坏）

# 4) 恢复失败回滚
#    用步骤 1 的快照重新执行一次 --restore
```

## 注意
- `--restore` 会**覆盖**目标库现有数据——演练前务必先备份
- 恢复后 Redis 额度计数不含历史（跨月自然失效，属预期）；如需保留可执行
  `redis-cli --scan --pattern "quota:*"` 手动核对
- OSS 云存储上传需配置阿里云凭证（`ALIYUN_OSS_*`），当前版本仅本地备份；
  接入点在 backup.sh 清理前插入上传步骤即可扩展
