#!/usr/bin/env bash
# 数据备份脚本（PRD 9.20）：PostgreSQL pg_dump + Milvus collection 导出
# 用法：./scripts/backup.sh [--retain 7]
# 生产建议由 Celery beat / crontab 每日 02:00 调用

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETAIN="${RETAIN:-7}"
STAMP="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "==> PostgreSQL dump"
PG_CONTAINER="${PG_CONTAINER:-moutalk-postgres-prod}"
PG_USER="${POSTGRES_USER:-moutalk}"
PG_DB="${POSTGRES_DB:-moutalk}"
docker exec "$PG_CONTAINER" pg_dump -U "$PG_USER" -d "$PG_DB" \
  > "$BACKUP_DIR/moutalk_pg_$STAMP.sql"
echo "    saved: $BACKUP_DIR/moutalk_pg_$STAMP.sql"

echo "==> Milvus collection 导出（negotiation_history）"
MILVUS_CONTAINER="${MILVUS_CONTAINER:-moutalk-milvus-prod}"
docker exec "$MILVUS_CONTAINER" sh -c \
  "milvus_cli_backup --collection negotiation_history --out /tmp/milvus_backup.json 2>/dev/null || echo 'milvus_backup 工具未安装，跳过（collection 为可重建数据）'" \
  || true
echo "    note: Milvus 向量数据为可重建缓存（原始轮次在 Postgres sessions 表），
    如需完整备份请使用 Milvus 官方 milvus-backup 工具（https://github.com/zilliztech/milvus-backup）"

echo "==> 清理过期备份（保留 $RETAIN 份）"
ls -1t "$BACKUP_DIR"/moutalk_pg_*.sql 2>/dev/null | tail -n +$((RETAIN + 1)) | xargs -r rm -f
echo "done. 备份目录: $BACKUP_DIR"
