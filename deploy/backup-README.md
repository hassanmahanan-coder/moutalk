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

## 恢复
```bash
# Postgres
cat backups/moutalk_pg_YYYYMMDD_HHMMSS.sql | docker exec -i moutalk-postgres-prod psql -U moutalk -d moutalk
```
